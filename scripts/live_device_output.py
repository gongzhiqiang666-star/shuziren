"""Explicit camera and audio devices; no silent fallback to default hardware."""
import hashlib
import time
import numpy as np


class VirtualCameraOutput:
    def __init__(self,width,height,backend='obs',device=None):
        import pyvirtualcam
        self.width=width;self.height=height;self.closed=False;self.frames=0
        started=time.perf_counter();self.open_attempts=0
        for attempt in range(11):
            self.open_attempts+=1
            try:
                self.camera=pyvirtualcam.Camera(width=width,height=height,fps=25,
                    fmt=pyvirtualcam.PixelFormat.BGR,backend=backend,device=device)
                break
            except RuntimeError as error:
                if attempt==10 or 'virtual camera output could not be started' not in str(error):raise
                time.sleep(.05)
        self.open_seconds=time.perf_counter()-started
        self.device=self.camera.device

    def send(self,index,image):
        if self.closed:raise RuntimeError('Camera output stopped')
        if type(index) is not int or index!=self.frames or image.dtype!=np.uint8 or image.shape!=(self.height,self.width,3):
            raise ValueError('Expected next correctly sized BGR frame')
        self.camera.send(np.ascontiguousarray(image));self.frames+=1

    def close(self):
        if not self.closed:self.closed=True;self.camera.close()


class VirtualAudioOutput:
    """Blocking PCM output. A device clock; not yet a combined A/V scheduler."""
    def __init__(self,device):
        import sounddevice as sd
        if type(device) is not int:raise ValueError('Explicit audio device index required')
        info=sd.query_devices(device)
        if info['max_output_channels']<1:raise ValueError('Selected device cannot output audio')
        settings=sd.WasapiSettings(auto_convert=True) if sd.query_hostapis(info['hostapi'])['name']=='Windows WASAPI' else None
        sd.check_output_settings(device=device,channels=1,dtype='int16',samplerate=24000,extra_settings=settings)
        self.stream=sd.RawOutputStream(device=device,samplerate=24000,channels=1,dtype='int16',extra_settings=settings)
        self.closed=False;self.samples=0;self.underflows=0;self.pcm_hash=hashlib.sha256()
        try:self.stream.start()
        except BaseException:self.stream.close();raise

    def write(self,pcm):
        if self.closed:raise RuntimeError('Audio output stopped')
        if not isinstance(pcm,bytes) or not pcm or len(pcm)%2:raise ValueError('PCM16 mono bytes required')
        underflow=self.stream.write(pcm)
        self.underflows+=int(underflow);self.samples+=len(pcm)//2;self.pcm_hash.update(pcm)
        return bool(underflow)

    def close(self,abort=False):
        if self.closed:return
        self.closed=True
        try:
            if abort:self.stream.abort()
            else:self.stream.stop()
        finally:self.stream.close()
