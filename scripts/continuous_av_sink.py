"""One timestamped NUT input feeds the installed FFmpeg NVENC/AAC encoder."""
from fractions import Fraction
import hashlib
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import av
import numpy as np


class ContinuousAVSink:
    def __init__(self,ffmpeg,output,width,height):
        self.output=Path(output).resolve()
        if self.output.exists():raise ValueError('Continuous output must be a new file')
        self.output.parent.mkdir(parents=True,exist_ok=True)
        self.width=width;self.height=height;self.frames=0;self.samples=0;self.closed=False;self.pcm_hash=hashlib.sha256()
        self.log=tempfile.TemporaryFile();self.container=None;self.lock=threading.RLock()
        command=[str(ffmpeg),'-nostdin','-y','-v','error','-probesize','32','-analyzeduration','0',
            '-f','nut','-i','pipe:0','-map','0:v:0','-map','0:a:0','-c:v','h264_nvenc','-preset','p4',
            '-bf','0','-g','50','-cq','18','-b:v','0','-pix_fmt','yuv420p','-c:a','aac',
            '-flush_packets','1','-muxdelay','0','-muxpreload','0','-f','mpegts',str(self.output)]
        try:
            self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.log)
            self.container=av.open(self.process.stdin,'w',format='nut')
            self.video=self.container.add_stream('rawvideo',rate=25);self.video.width=width;self.video.height=height;self.video.pix_fmt='bgr24'
            self.audio=self.container.add_stream('pcm_s16le',rate=24000);self.audio.layout='mono';self.audio.format='s16'
        except BaseException:
            self.abort();raise

    def submit(self,frame_index,image,pcm):
        with self.lock:return self._submit(frame_index,image,pcm)

    def _submit(self,frame_index,image,pcm):
        if self.closed:raise RuntimeError('Continuous output stopped')
        if frame_index!=self.frames or image.shape!=(self.height,self.width,3) or image.dtype!=np.uint8 or len(pcm)!=1920:
            raise ValueError('Expected next BGR frame and exactly 960 PCM samples')
        started=time.perf_counter_ns()
        if image.flags.c_contiguous and hasattr(av.VideoFrame, 'from_numpy_buffer'):
            video = av.VideoFrame.from_numpy_buffer(image, format='bgr24')
        else:
            video = av.VideoFrame.from_ndarray(image, format='bgr24')
        video.pts=frame_index;video.time_base=Fraction(1,25)
        audio=av.AudioFrame.from_ndarray(np.frombuffer(pcm,dtype='<i2').reshape(1,-1),format='s16',layout='mono')
        audio.sample_rate=24000;audio.pts=self.samples;audio.time_base=Fraction(1,24000)
        prepared=time.perf_counter_ns()
        try:
            self.container.mux(self.video.encode(video));video_written=time.perf_counter_ns()
            self.container.mux(self.audio.encode(audio))
        except BaseException:self.abort();raise
        self.frames+=1;self.samples+=960;self.pcm_hash.update(pcm)
        return {'prepare_ns':prepared-started,'video_mux_ns':video_written-prepared,
            'audio_mux_ns':time.perf_counter_ns()-video_written}

    def close(self):
        with self.lock:return self._close()

    def _close(self):
        if self.closed:return
        try:
            self.container.mux(self.video.encode(None));self.container.mux(self.audio.encode(None));self.container.close();self.container=None
            self.process.stdin.close();code=self.process.wait(timeout=30)
            if code:
                self.log.seek(0);raise RuntimeError('Continuous encoder failed: '+self.log.read()[-2000:].decode(errors='replace'))
        except BaseException:self.abort();raise
        self.closed=True;self.log.close()

    def abort(self):
        # Stop the reader before waiting for a thread blocked in AVIO.write.
        if hasattr(self,'process') and self.process.poll() is None:self.process.kill()
        with self.lock:return self._abort()

    def _abort(self):
        if self.closed:return
        self.closed=True
        if hasattr(self,'process'):
            if self.process.poll() is None:self.process.kill()
            self.process.wait(timeout=10)
            # Kill first, so a blocked AVIO flush cannot keep the producer alive.
            if self.container:
                try:self.container.close()
                except Exception:pass
                self.container=None
            if self.process.stdin:
                try:self.process.stdin.close()
                except (OSError,ValueError):pass
        self.log.close();self.output.unlink(missing_ok=True)
