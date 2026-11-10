"""Restore one complete utterance on disk, preserving PCM feature context."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import uuid
import wave


@dataclass(frozen=True)
class Utterance:
    session_id:str
    task_id:str
    script_id:str
    path:Path
    samples:int
    original_sha256:str
    pcm_sha256:str


class SpeechAssembler:
    def __init__(self,directory):
        self.root=Path(directory).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.pending=None;self.sequence=None;self.session=None

    def push(self,packet):
        try:
            origin=packet.origin
            if origin is None or not origin.original_pcm_sha256:raise ValueError('Complete utterance provenance required')
            if self.session is None:self.session=packet.session
            if packet.session!=self.session:raise ValueError('Old or interleaved session')
            if self.sequence is not None and packet.sequence!=self.sequence+1:raise ValueError('Missing/repeated speech packet')
            if len(packet.pcm)!=packet.samples*2 or packet.samples<=0:raise ValueError('Invalid PCM packet')
            if self.pending is None:
                if origin.start_sample!=0:raise ValueError('First packet must start at zero')
                path=self.root/(str(uuid.uuid4())+'.wav')
                writer=wave.open(str(path),'wb');writer.setparams((1,2,24000,0,'NONE','not compressed'))
                self.pending={'path':path,'writer':writer,'origin':origin,'samples':0,'hash':hashlib.sha256()}
            pending=self.pending;first=pending['origin']
            if any(getattr(origin,key)!=getattr(first,key) for key in ['task_id','script_id','original_sha256','total_samples','original_pcm_sha256']):
                raise ValueError('Interleaved or changed utterance')
            if origin.start_sample!=pending['samples'] or pending['samples']+packet.samples>origin.total_samples:
                raise ValueError('Non-contiguous utterance range')
            pending['writer'].writeframesraw(packet.pcm);pending['hash'].update(packet.pcm);pending['samples']+=packet.samples
            self.sequence=packet.sequence
            if pending['samples']<origin.total_samples:return None
            if pending['hash'].hexdigest()!=origin.original_pcm_sha256:raise ValueError('Complete utterance PCM fingerprint mismatch')
            pending['writer'].close();self.pending=None
            return Utterance(packet.session.id,origin.task_id,origin.script_id,pending['path'],origin.total_samples,origin.original_sha256,origin.original_pcm_sha256)
        except BaseException:
            self.close();raise

    def close(self):
        if self.pending:
            pending=self.pending;self.pending=None
            try:pending['writer'].close()
            finally:
                if pending['path'].parent==self.root:pending['path'].unlink(missing_ok=True)
        self.sequence=None;self.session=None
