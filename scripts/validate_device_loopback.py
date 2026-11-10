"""Real virtual-device send/receive probes; no platform or physical sound claim."""
import argparse
import json
from pathlib import Path
import subprocess
import threading
import time
import uuid
import av
import numpy as np
from scipy import signal
from scripts.live_device_output import VirtualCameraOutput,VirtualAudioOutput


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ffmpeg',required=True,type=Path)
    parser.add_argument('--audio-output',required=True,type=int);parser.add_argument('--audio-input',required=True,type=int)
    parser.add_argument('--camera-input',default='C920');parser.add_argument('--report-directory',required=True,type=Path)
    args=parser.parse_args();root=args.report_directory/('run-'+uuid.uuid4().hex);root.mkdir(parents=True)
    report={'status':'failed','combined_av_sync_tested':False,'physical_sound_tested':False,'platform_tested':False}
    camera=None;audio=None;capture=None;process=None;stopped=threading.Event();thread=None
    try:
        import sounddevice as sd
        received=[];capture_errors=[];captured_samples=[0]
        def record(data,frames,timing,status):
            if status:capture_errors.append(str(status))
            if captured_samples[0]+frames>48000*8:raise sd.CallbackAbort()
            received.append(np.frombuffer(bytes(data),dtype='<i2').copy());captured_samples[0]+=frames
        capture=sd.RawInputStream(device=args.audio_input,samplerate=48000,channels=1,dtype='int16',callback=record)
        capture.start();time.sleep(.2)
        audio=VirtualAudioOutput(args.audio_output)
        rng=np.random.default_rng(20261111)
        original=signal.lfilter(signal.firwin(65,3000,fs=24000),[1],rng.standard_normal(48000))
        original=np.asarray(np.clip(original*4000,-12000,12000),dtype='<i2')
        for start in range(0,len(original),960):audio.write(original[start:start+960].tobytes())
        audio.close();time.sleep(.3);capture.stop();capture.close();capture=None
        recorded=np.concatenate(received);reference=signal.resample_poly(original.astype(float),2,1)
        correlation=signal.correlate(recorded.astype(float),reference,mode='valid',method='fft')
        offset=int(np.argmax(correlation));aligned=recorded[offset:offset+len(reference)].astype(float)
        coefficient=float(np.dot(aligned,reference)/(np.linalg.norm(aligned)*np.linalg.norm(reference)))
        report['audio']={'output_device':args.audio_output,'input_device':args.audio_input,'sent_samples_24k':audio.samples,
            'captured_samples_48k':len(recorded),'correlation':coefficient,'capture_offset_samples':offset,
            'output_underflows':audio.underflows,'capture_status':capture_errors,'source_pcm_sha256':audio.pcm_hash.hexdigest()}
        if coefficient<.95 or audio.underflows or capture_errors:raise RuntimeError('Audio device loopback failed')
        camera=VirtualCameraOutput(720,1280)
        send_errors=[];sent=[0]
        def send():
            try:
                origin=time.perf_counter()
                while not stopped.is_set():
                    index=sent[0];image=np.full((1280,720,3),96,np.uint8)
                    # Gray patches survive the driver's color conversion.
                    for bit in range(8):image[80:160,40+bit*80:100+bit*80]=224 if (index%256)&(1<<bit) else 32
                    camera.send(index,image);sent[0]+=1
                    stopped.wait(max(0,origin+sent[0]/25-time.perf_counter()))
            except BaseException as error:send_errors.append(str(error));stopped.set()
        thread=threading.Thread(target=send);thread.start()
        with (root/'camera-capture.log').open('wb') as log:
            command=[str(args.ffmpeg),'-nostdin','-y','-hide_banner','-loglevel','error','-f','dshow',
                '-video_size','720x1280','-framerate','25','-i','video='+args.camera_input,
                '-frames:v','25','-an','-c:v','ffv1',str(root/'camera.mkv')]
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log)
            process.wait(timeout=15)
        stopped.set();thread.join(2)
        if process.returncode or send_errors:raise RuntimeError('Camera capture failed: '+str(send_errors))
        markers=[]
        with av.open(str(root/'camera.mkv')) as container:
            for frame in container.decode(video=0):
                image=frame.to_ndarray(format='bgr24');value=0
                for bit in range(8):
                    if image[90:150,50+bit*80:90+bit*80].mean()>128:value|=1<<bit
                markers.append(value)
        steps=[(b-a)%256 for a,b in zip(markers,markers[1:])]
        report['camera']={'sender_device':camera.device,'receiver_device':args.camera_input,'sent_frames':sent[0],
            'received_frames':len(markers),'markers':markers,'marker_steps':steps,'unique_markers':len(set(markers))}
        if len(markers)!=25 or len(set(markers))<20 or any(step>3 for step in steps):raise RuntimeError('Camera marker continuity failed')
        camera.close();camera=None;report['status']='passed'
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        stopped.set()
        if process and process.poll() is None:process.kill();process.wait(timeout=5)
        if thread:thread.join(2)
        if camera:camera.close()
        if capture:capture.abort();capture.close()
        if audio:audio.close(abort=True)
        (root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(root/'result.json'),**report},ensure_ascii=False));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
