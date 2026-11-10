"""Direct raw BGR -> H.264/AAC MP4; explicit encoder, no silent fallback."""
from pathlib import Path
import subprocess
import tempfile
import numpy as np


class RawVideoWriter:
    def __init__(self,ffmpeg,output,audio,width,height,encoder='h264_nvenc'):
        if encoder not in {'h264_nvenc','libx264'}:raise ValueError('Unsupported encoder')
        self.output=Path(output);self.width=int(width);self.height=int(height)
        if min(self.width,self.height)<=0 or self.width%2 or self.height%2:
            raise ValueError('Video dimensions must be positive even numbers')
        if self.output.exists():raise ValueError('Output must be a new file')
        self.output.parent.mkdir(parents=True,exist_ok=True)
        self.log=tempfile.TemporaryFile();self.closed=False;self.frames=0
        codec=['-c:v','h264_nvenc','-preset','p4','-cq','18','-b:v','0'] if encoder=='h264_nvenc' else ['-c:v','libx264','-preset','medium','-crf','18']
        command=[str(ffmpeg),'-nostdin','-y','-v','error','-f','rawvideo','-pix_fmt','bgr24',
            '-s',f'{self.width}x{self.height}','-r','25','-i','pipe:0','-i',str(audio),
            '-map','0:v:0','-map','1:a:0',*codec,'-pix_fmt','yuv420p','-c:a','aac',
            '-movflags','+faststart',str(self.output)]
        try:self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.log)
        except BaseException:self.log.close();raise

    def isOpened(self):return not self.closed and self.process.poll() is None

    def _error(self):
        self.log.seek(0,2);size=self.log.tell();self.log.seek(max(0,size-2000))
        return self.log.read().decode('utf-8',errors='replace')

    def write(self,frame):
        if self.closed:raise RuntimeError('Encoder is closed')
        if frame.shape!=(self.height,self.width,3) or frame.dtype!=np.uint8:
            raise ValueError('Expected an HxWx3 uint8 BGR frame')
        try:
            data=memoryview(np.ascontiguousarray(frame)).cast('B')
            while data:
                count=self.process.stdin.write(data)
                if not count:raise BrokenPipeError('Encoder input closed')
                data=data[count:]
            self.frames+=1
        except (BrokenPipeError,OSError) as error:
            self.abort()
            raise RuntimeError('Direct encoder failed: '+self.failure) from error

    def release(self):
        if self.closed:return
        try:
            self.process.stdin.close()
            code=self.process.wait(timeout=60)
            if code or not self.frames:raise RuntimeError('Direct encoder failed: '+self._error())
        except BaseException:
            self.abort();raise
        else:self.closed=True;self.log.close()

    def abort(self):
        if self.closed:return
        if self.process.poll() is None:self.process.kill()
        self.process.wait(timeout=10)
        try:self.process.stdin.close()
        except (BrokenPipeError,OSError):pass
        self.failure=self._error();self.log.close();self.closed=True
        self.output.unlink(missing_ok=True)
