"""Combined real camera/audio capture with matched visual and PCM markers."""
import argparse
import json
from pathlib import Path
import subprocess
import threading
import time
import uuid
import av
import numpy as np
from scripts.live_av_device_sink import AVDeviceSink
from scripts.av_sync_markers import is_flash,analyze_markers


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ffmpeg',type=Path,required=True)
    parser.add_argument('--audio-output',type=int,required=True);parser.add_argument('--report-directory',type=Path,required=True)
    parser.add_argument('--video-delay-ms',type=float,default=0)
    parser.add_argument('--camera-input',default='C920')
    args=parser.parse_args();root=args.report_directory/('run-'+uuid.uuid4().hex);root.mkdir(parents=True)
    report={'status':'failed','physical_sound_tested':False,'platform_tested':False,'avatar_inference_tested':False}
    sink=None;process=None;trace=[];sender=None;sender_errors=[];first_frame=threading.Event()
    try:
        def presented(row):
            trace.append(row)
            if row['event']=='video_sent':first_frame.set()
        # Match ConsoleLive's production device path.  The previous validator
        # used the legacy two-frame/BGR/free-running configuration instead of
        # the current I420/smoothed-clock path.
        sink=AVDeviceSink(720,1280,args.audio_output,on_present=presented,
                          video_delay_ms=args.video_delay_ms,smooth_clock=True,
                          buffer_frames=8,camera_i420=True)
        def send():
            try:
                for index in range(8,150):
                    image=np.full((1280,720,3),96,np.uint8)
                    for bit in range(8):image[80:160,40+bit*80:100+bit*80]=224 if index&(1<<bit) else 32
                    image[200:320,40:680]=224 if is_flash(index) else 32
                    pcm=np.zeros(960,dtype='<i2')
                    if index in [25,65,105]:pcm=np.asarray(5000*np.sin(2*np.pi*1000*np.arange(960)/24000),dtype='<i2')
                    sink.submit(index,image,pcm.tobytes())
                sink.draining=True
            except BaseException as error:sender_errors.append(str(error))
        for index in range(8):
            image=np.full((1280,720,3),96,np.uint8)
            for bit in range(8):image[80:160,40+bit*80:100+bit*80]=224 if index&(1<<bit) else 32
            sink.submit(index,image,bytes(1920))
        sender=threading.Thread(target=send);sender.start()
        if not first_frame.wait(2):raise RuntimeError('Camera did not start sending')
        with (root/'capture.log').open('wb') as log:
            process=subprocess.Popen([str(args.ffmpeg),'-nostdin','-y','-hide_banner','-loglevel','error',
                '-use_wallclock_as_timestamps','1','-f','dshow','-audio_buffer_size','20','-video_size','720x1280','-framerate','25','-i',
                f'video={args.camera_input}:audio=CABLE Output (VB-Audio Virtual Cable)',
                '-t','5','-c:v','ffv1','-c:a','pcm_s16le',str(root/'receiver.mkv')],stdout=subprocess.DEVNULL,stderr=log)
            process.wait(timeout=15)
            if process.returncode:
                sink.abort(); sender.join(3)
                raise RuntimeError('Combined receiver failed; see capture.log')
        sender.join(3)
        if sender.is_alive() or sender_errors:raise RuntimeError('Device sender failed: '+str(sender_errors))
        sink.close()
        if process.returncode:raise RuntimeError('Combined receiver failed; see capture.log')
        markers=[];audio=[];audio_times=[];rate=None
        with av.open(str(root/'receiver.mkv')) as container:
            for packet in container.demux():
                for frame in packet.decode():
                    if isinstance(frame,av.VideoFrame):
                        image=frame.to_ndarray(format='bgr24');value=0
                        for bit in range(8):
                            if image[90:150,50+bit*80:90+bit*80].mean()>128:value|=1<<bit
                        markers.append((value,float(frame.pts*frame.time_base),bool(image[220:300,60:660].mean()>128)))
                    else:
                        samples=frame.to_ndarray().reshape(-1,frame.layout.nb_channels).mean(axis=1)
                        rate=frame.sample_rate;audio.append(samples)
                        audio_times.append(float(frame.pts*frame.time_base)+np.arange(len(samples))/rate)
        samples=np.concatenate(audio);times=np.concatenate(audio_times)
        active=np.flatnonzero(np.abs(samples)>1000)
        starts=active[np.r_[True,np.diff(active)>rate*.1]]
        pulses=[float(times[index]) for index in starts];offsets=[]
        report.update(audio_marker_times=pulses,markers=markers,video_delay_ms=args.video_delay_ms,
            receiver_audio_buffer_ms=20,queue_peak=sink.peak,underflows=sink.underflows,
            received_video_frames=len(markers),unique_markers=len(set(value for value,_,_ in markers)))
        report.update(analyze_markers(markers,pulses))
        report.update(sent_frames=sink.frames,presented_frames=sink.presented,queue_peak=sink.peak,underflows=sink.underflows,
            video_delay_ms=args.video_delay_ms,receiver_audio_buffer_ms=20,
            received_video_frames=len(markers),unique_markers=len(set(value for value,_,_ in markers)),
            audio_marker_times=pulses,markers=markers,
            timing_acceptance=False)
        if not report['receiver_sync_passed']:raise RuntimeError('Combined receiver exceeds 80ms A/V marker tolerance')
        report['status']='passed'
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        if sink:sink.abort()
        if sender:sender.join(3)
        report.update(sender_errors=sender_errors,device_error=sink.error if sink else None,
            submitted_frames=sink.frames if sink else 0,presented_frames=sink.presented if sink else 0)
        if process and process.poll() is None:process.kill();process.wait(timeout=5)
        (root/'device-presented.json').write_text(json.dumps(trace),encoding='utf-8')
        (root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(root/'result.json'),'status':report['status'],'error':report.get('error'),'av_offset_ms':report.get('av_offset_ms')},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
