"""Parent-owned persistent TTS process and version-bound result acceptance."""
import json
import hashlib
from pathlib import Path
import subprocess
import threading
import uuid

from scripts.product_store import Conflict, ProductError, ProductStore
from scripts.voice_store import VoiceStore


class TTSTasks:
    def __init__(self,runtime_root,data_directory):
        self.runtime=Path(runtime_root).resolve();self.data=Path(data_directory).resolve()
        self.products=ProductStore(self.data);self.voices=VoiceStore(self.data)
        self.path=self.data/'tts-task.json'
        self.lock=threading.RLock();self.process=None;self.monitor=None;self.log=None;self.closed=False;self.worker_usable=False
        self.task=None
        if self.path.exists():
            self.task=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.task,dict) or self.task.get('status') not in {'running','succeeded','failed','cancelled','interrupted'}:
                raise ProductError('TTS任务记录损坏')
            if self.task['status']=='running':
                self.task.update(status='interrupted',error='服务已中断，请重新合成');self._save()

    def _save(self):
        temporary=self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.task,ensure_ascii=False),encoding='utf-8');temporary.replace(self.path)

    def state(self):
        with self.lock:
            if self.task and self.task['status']=='succeeded':
                try:
                    product=self.products.get(self.task['product_id'])
                    voice=self.voices.get(self.task['voice_id'])
                    valid=(product['version']==self.task['product_version']
                        and (self.task.get('kind')=='reply' or self.products.selected_script(product['id'])==self.task['script_id'])
                        and self.voices.selected()==voice['id']
                        and voice['audio_sha256']==self.task['voice_audio_sha256']
                        and voice['text_sha256']==self.task['voice_text_sha256'])
                except Exception: valid=False
                if not valid:
                    self.task.update(status='failed',error='已完成音频的输入已变化，结果失效，请重新合成')
                    self.task['previous_result']=self.task.pop('result',None);self._save()
            return dict(self.task) if self.task else None

    def _start_worker(self):
        if self.process and self.process.poll() is None and self.worker_usable: return self.process
        self._stop_worker()
        python=self.runtime/'_internal/env/python.exe'
        if not python.is_file(): raise ProductError('缺少TTS运行解释器')
        self.log=(self.data/'tts-worker.log').open('a',encoding='utf-8')
        try:
            self.process=subprocess.Popen([str(python),'-X','utf8','-m','scripts.tts_worker',
                '--runtime-root',str(self.runtime),'--data-directory',str(self.data)],
                cwd=Path(__file__).resolve().parents[1],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=self.log,text=True,encoding='utf-8',bufsize=1,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except Exception:
            self.log.close();self.log=None;raise
        self.worker_usable=True
        return self.process

    def audio(self,task_id):
        with self.lock:
            state=self.state()
            if not state or state['id']!=task_id or state['status']!='succeeded':
                raise Conflict('音频任务不存在、未完成或已失效')
            result=state['result'];path=Path(result['output']).resolve()
            if path.parent!=(self.data/'tts').resolve(): raise ProductError('音频路径越界')
            content=path.read_bytes()
            if hashlib.sha256(content).hexdigest()!=result['sha256']:
                raise Conflict('音频文件已变化，请重新合成')
            return content

    def _stop_worker(self):
        self.worker_usable=False
        if self.process:
            if self.process.poll() is None: self.process.terminate()
            self.process.wait(timeout=10)
            if self.process.stdin: self.process.stdin.close()
            if self.process.stdout: self.process.stdout.close()
            self.process=None
        if self.log: self.log.close();self.log=None

    def snapshot_audio(self,task_id,destination):
        """Copy a completed immutable task to an exclusive owned staging file."""
        destination=Path(destination);created=False
        with self.lock:
            state=self.state()
            if not state or state['id']!=task_id or state['status']!='succeeded':
                raise Conflict('音频任务不存在、未完成或已失效')
            source=Path(state['result']['output']).resolve()
            if source.parent!=(self.data/'tts').resolve():raise ProductError('音频路径越界')
            try:
                value=hashlib.sha256()
                with source.open('rb') as reader,destination.open('xb') as writer:
                    created=True
                    for block in iter(lambda:reader.read(1024*1024),b''):
                        writer.write(block);value.update(block)
                if value.hexdigest()!=state['result']['sha256']:
                    raise Conflict('音频文件已变化，请重新合成')
                current=self.state()
                if not current or current['id']!=task_id or current['status']!='succeeded':
                    raise Conflict('音频输入在快照期间发生变化')
                return json.loads(json.dumps(state))
            except BaseException:
                if created:destination.unlink(missing_ok=True)
                raise

    def start(self,product_id,script_id,voice_id,speed=1.0,language='zh-CN',use_cache=False):
        with self.lock:
            if self.closed: raise Conflict('TTS服务正在退出')
            if self.task and self.task['status']=='running': raise Conflict('已有语音合成任务')
            product=self.products.get(product_id)
            if self.products.selected_script(product_id)!=script_id: raise Conflict('请先选用当前商品版本的话术')
            script=next((s for s in self.products.scripts(product_id) if s['id']==script_id),None)
            if script is None or not 1<=len(script['text'].strip())<=2000: raise ProductError('当前合成支持1至2000字话术')
            voice=self.voices.get(voice_id)
            if self.voices.selected()!=voice_id: raise Conflict('请先选用该音色')
            if type(speed) not in (int,float) or not .5<=speed<=2 or type(use_cache) is not bool:
                raise ProductError('语速或缓存参数无效')
            if not isinstance(language,str) or not language: raise ProductError('请选择语言')
            return self._submit(product, script_id, voice, script['text'], speed, language, use_cache)

    def start_reply(self, product, voice_id, text):
        with self.lock:
            if self.closed or (self.task and self.task['status']=='running'):
                raise Conflict('语音合成正在占用，请稍后重试')
            if self.products.get(product['id']) != product or self.voices.selected() != voice_id:
                raise Conflict('回复所用商品或音色已变化')
            if not isinstance(text,str) or not 1<=len(text.strip())<=240:
                raise ProductError('回复长度须为1至240字')
            voice=self.voices.get(voice_id)
            return self._submit(product, 'reply-'+uuid.uuid4().hex, voice, text, 1., 'zh-CN', False, kind='reply')

    def _submit(self, product, script_id, voice, text, speed, language, use_cache, *, kind=None):
        process=self._start_worker()
        self.task={'id':str(uuid.uuid4()),'status':'running','product_id':product['id'],
            'product_version':product['version'],'script_id':script_id,'voice_id':voice['id']}
        if kind:self.task['kind']=kind
        self.task.update(voice_audio_sha256=voice['audio_sha256'],voice_text_sha256=voice['text_sha256'])
        self.task.update(product_title=product['title'],speed=speed,language=language,use_cache=use_cache)
        self._save()
        request={'voice_id':voice['id'],'text':text,'speed':speed,'language':language,'use_cache':use_cache}
        task_id=self.task['id']
        self.monitor=threading.Thread(target=self._run,args=(process,request,product,voice,task_id),daemon=True)
        self.monitor.start()
        return dict(self.task)

    def _run(self,process,request,product,voice,task_id):
        timer=threading.Timer(180,self._expire,args=(task_id,));timer.daemon=True;timer.start()
        try:
            process.stdin.write(json.dumps(request,ensure_ascii=False)+'\n');process.stdin.flush()
            while True:
                line=process.stdout.readline()
                if not line: raise ProductError('TTS工作进程中断')
                event=json.loads(line)
                if event.get('event')=='ready': continue
                if not event.get('ok'): raise ProductError('TTS生成失败，请检查工作进程日志')
                result=event['result'];break
            with self.lock:
                if self.task['id']!=task_id or self.task['status']!='running' or self.closed: return
                if (self.products.get(product['id'])!=product
                    or (self.task.get('kind')!='reply' and self.products.selected_script(product['id'])!=self.task['script_id'])
                    or self.voices.get(voice['id'])!=voice or self.voices.selected()!=voice['id']):
                    raise Conflict('商品、选用稿或音色已变化，旧音频不再作为当前结果')
                output=Path(result['output']).resolve()
                if output.parent!=(self.data/'tts').resolve() or not output.is_file():
                    raise ProductError('TTS结果文件无效或越界')
                if result.get('voice_id')!=voice['id'] or hashlib.sha256(output.read_bytes()).hexdigest()!=result.get('sha256'):
                    raise ProductError('TTS结果音色或内容指纹不符')
                self.task.update(status='succeeded',result=result);self._save()
        except Exception:
            with self.lock:
                if self.task['id']==task_id and self.task['status']=='running':
                    self.worker_usable=False
                    self.task.update(status='failed',error='合成失败或输入已变化，未接受本次音频；请检查输入后重试');self._save()
                    if process.poll() is None: process.terminate()
        finally:
            timer.cancel()

    def _expire(self,task_id):
        with self.lock:
            if self.task and self.task['id']==task_id and self.task['status']=='running':
                self.task.update(status='failed',error='合成超过180秒，工作进程已终止');self._save()
                self.worker_usable=False
                if self.process and self.process.poll() is None: self.process.terminate()

    def cancel(self,task_id):
        with self.lock:
            if not self.task or self.task['id']!=task_id: raise ProductError('TTS任务不存在')
            if self.task['status']=='running':
                self.task['status']='cancelled';self._save()
                self.worker_usable=False
                if self.process and self.process.poll() is None: self.process.terminate()
            monitor=self.monitor
        if monitor: monitor.join(timeout=12)
        with self.lock:
            if self.task['status']=='cancelled': self._stop_worker()
            return dict(self.task)

    def close(self):
        with self.lock:
            self.closed=True;task_id=self.task['id'] if self.task else None
        if task_id: self.cancel(task_id)
        with self.lock: self._stop_worker()
