"""Validated TTS snapshot -> bounded speech queue; no device output yet."""
from pathlib import Path
import threading
import uuid

from scripts.live_speech_queue import LiveSpeechQueue,SpeechOrigin,StaleSession
from scripts.product_store import Conflict,ProductError
from scripts.speech_chunks import iter_wav_file_chunks


class LiveSpeechIngress:
    def __init__(self,tts,avatars,data_directory,queue=None):
        self.tts=tts;self.avatars=avatars;self.queue=queue or LiveSpeechQueue()
        self.root=(Path(data_directory)/'live-speech-inputs').resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.session=None;self.context=None;self.pending=None
        self.last_task_id=None;self.error=None

    def _binding(self, verify_assets=False):
        product_id=self.tts.products.selected();voice_id=self.tts.voices.selected();avatar_id=self.avatars.selected_id()
        if not all([product_id,voice_id,avatar_id]):raise Conflict('请先选择商品、音色和形象')
        product=self.tts.products.get(product_id);voice=self.tts.voices.get(voice_id)
        avatar=(self.avatars.get if verify_assets else self.avatars.identity)(avatar_id)
        return {'product_id':product_id,'product_version':product['version'],'voice_id':voice_id,'avatar_id':avatar_id,
            'voice_audio_sha256':voice['audio_sha256'],'voice_text_sha256':voice['text_sha256'],
            'avatar_manifest_sha256':avatar['manifest_sha256']}

    def start(self):
        with self.lock:
            self.stop();binding=self._binding(verify_assets=True)
            self.session=self.queue.start({key:binding[key] for key in ['product_id','product_version','voice_id','avatar_id']})
            self.context=binding;self.last_task_id=None;self.error=None
            return self.session

    def _drop_pending(self):
        if self.pending:
            pending=self.pending;self.pending=None
            pending['iterator'].close();path=pending['path']
            if path.parent.parent!=self.root:raise ProductError('交接快照路径越界')
            path.unlink(missing_ok=True)
            try:path.parent.rmdir()
            except OSError:pass

    def stop(self):
        with self.lock:
            self.queue.stop();self.session=None;self.context=None;self._drop_pending()

    def _validate(self):
        if self.session is None:raise StaleSession('语音交接场次已停止')
        if not self.queue.is_current(self.session):
            self.stop();raise StaleSession('语音交接场次已停止')
        try:
            if self._binding()!=self.context:raise Conflict('商品版本、参考音色或形象已变化')
        except (ValueError,OSError) as error:
            self.error=str(error);self.stop();raise Conflict('交接输入已变化，旧场次已停止') from error

    def capture(self,task_id,*,rotation_item=None):
        if not isinstance(task_id,str) or not task_id:raise ProductError('语音任务ID无效')
        with self.lock:
            self._validate()
            if task_id==self.last_task_id:raise Conflict('该语音任务已交接，不重复入队')
            if self.pending:raise Conflict('上一条音频仍在背压交接，请先消费队列')
            directory=self.root/self.session.id;directory.mkdir(exist_ok=True)
            path=directory/(str(uuid.uuid4())+'.wav');iterator=None;owned=False
            try:
                state=self.tts.snapshot_audio(task_id,path)
                owned=True
                self._validate()
                expected=self.context if rotation_item is None else rotation_item
                keys=['product_id','product_version'] if rotation_item is None else ['product_id','product_version','script_id']
                if state.get('voice_id')!=expected.get('voice_id', self.context['voice_id']) or any(state.get(key)!=expected[key] for key in keys):
                    raise Conflict('语音不属于本场次商品版本或音色')
                iterator=iter_wav_file_chunks(path,self.queue.max_utterance_samples);chunk=next(iterator)
                if chunk.source_sha256!=state['result']['sha256']:raise Conflict('交接快照指纹不符')
                self.pending={'path':path,'iterator':iterator,'chunk':chunk,'task_id':task_id,'script_id':state['script_id']}
                self.last_task_id=task_id
                receipt={'task_id':task_id,'script_id':state['script_id'],'source_sha256':chunk.source_sha256,'samples':chunk.total_samples}
                self._pump();return {**receipt,**self.state(validate=False)}
            except BaseException:
                if self.pending and self.pending['path']==path:self._drop_pending()
                else:
                    if iterator:iterator.close()
                    if owned:path.unlink(missing_ok=True)
                    try:directory.rmdir()
                    except OSError:pass
                raise

    def _pump(self):
        try:
            while self.pending:
                pending=self.pending;chunk=pending['chunk']
                origin=SpeechOrigin(pending['task_id'],pending['script_id'],chunk.source_sha256,chunk.start_sample,chunk.total_samples,chunk.original_pcm_sha256)
                try:self.queue.put(self.session,chunk.audio,origin=origin)
                except TimeoutError:return
                try:pending['chunk']=next(pending['iterator'])
                except StopIteration:self._drop_pending()
        except BaseException as error:
            self.error=str(error);self.stop();raise

    def pump(self):
        with self.lock:self._validate();self._pump();return self.state(validate=False)

    def take(self,timeout=0):
        with self.lock:self._validate();session=self.session
        packet=self.queue.take(session,timeout)
        with self.lock:
            self._validate()
            if packet.session!=self.session:raise StaleSession('旧场次音频不可输出')
            self._pump()
        return packet

    def state(self,validate=True):
        with self.lock:
            if validate and self.session:
                try:self._validate()
                except Conflict:pass
            return {**self.queue.state(),'status':'running' if self.session else 'stopped',
                'pending_task_id':self.pending['task_id'] if self.pending else None,
                'last_task_id':self.last_task_id,'error':self.error}
