"""Version-bound product speech + avatar render, with owned process lifecycle."""
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import threading
import uuid

from scripts.avatar_store import AvatarStore,digest
from scripts.avatar_tasks import AvatarTasks
from scripts.product_store import Conflict,ProductError


class RenderTasks:
    def __init__(self,runtime_root,data_directory,tts):
        self.runtime=Path(runtime_root).resolve();self.data=Path(data_directory).resolve()
        self.data.mkdir(parents=True,exist_ok=True)
        self.jobs=self.data/'render-jobs';self.jobs.mkdir(exist_ok=True)
        self.path=self.data/'render-task.json';self.tts=tts;self.avatars=AvatarStore(self.data)
        self.lock=threading.RLock();self.process=self.monitor=None;self.closed=False;self.task=None
        if self.path.exists():
            self.task=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.task,dict) or self.task.get('status') not in {'running','succeeded','failed','cancelled','interrupted'}:
                raise ProductError('视频合成任务记录损坏')
            if self.task['status']=='running':
                self.task.update(status='interrupted',error='上次视频合成已中断，请重新生成');self._save()

    def _save(self):
        temporary=self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.task,ensure_ascii=False),encoding='utf-8');temporary.replace(self.path)

    def _inputs(self,tts_task_id,avatar_id):
        audio=self.tts.state()
        if not audio or audio['id']!=tts_task_id or audio['status']!='succeeded':
            raise Conflict('请先完成当前话术的语音合成')
        if self.tts.products.selected()!=audio['product_id']:
            raise Conflict('语音不属于当前选用商品，请重新选择并合成')
        if self.avatars.selected_id()!=avatar_id:
            raise Conflict('请先选用该形象')
        avatar=self.avatars.get(avatar_id)
        content=self.tts.audio(tts_task_id)
        binding={'tts_task_id':tts_task_id,'avatar_id':avatar_id,'avatar_manifest_sha256':avatar['manifest_sha256'],
                 'audio_sha256':hashlib.sha256(content).hexdigest(),'product_id':audio['product_id'],
                 'product_version':audio['product_version'],'script_id':audio['script_id'],'voice_id':audio['voice_id']}
        return binding,content,audio,avatar

    def _validate(self,task):
        binding,_,_,_=self._inputs(task['tts_task_id'],task['avatar_id'])
        if any(task.get(key)!=value for key,value in binding.items()):
            raise Conflict('视频输入已变化，请重新生成')

    def state(self):
        with self.lock:
            if self.task and self.task['status'] in {'running','succeeded'}:
                try:self._validate(self.task)
                except (ValueError,OSError) as error:
                    self.task.update(status='failed',error='商品、语音或形象已变化，本次视频已失效')
                    self.task.pop('result',None);self._save()
                    if self.process:AvatarTasks._terminate(self.process)
            return dict(self.task) if self.task else None

    def start(self,tts_task_id,avatar_id):
        if not all(isinstance(value,str) for value in (tts_task_id,avatar_id)):
            raise ProductError('语音任务或形象ID无效')
        with self.lock:
            if self.closed:raise Conflict('视频合成服务正在退出')
            if self.process is not None or (self.monitor and self.monitor.is_alive()):
                raise Conflict('已有视频合成任务，请等待或取消')
            binding,content,audio,avatar=self._inputs(tts_task_id,avatar_id)
            python=self.runtime/'_internal/env/python.exe'
            if not python.is_file():raise ProductError('缺少视频合成运行解释器')
            task_id=str(uuid.uuid4());work=self.jobs/task_id;work.mkdir()
            self.task={'id':task_id,'status':'running',**binding,'product_title':audio['product_title'],
                       'avatar_name':avatar['name'],'speed':audio['speed']}
            log=(work/'worker.log').open('wb')
            try:
                (work/'audio.wav').write_bytes(content);self._save()
                self.process=subprocess.Popen([str(python),'-X','utf8','-m','scripts.render_worker',
                    '--runtime-root',str(self.runtime),'--avatar-directory',str(self.avatars._directory(avatar_id)),
                    '--audio',str(work/'audio.wav'),'--output',str(work/'output.mp4')],
                    stdout=subprocess.PIPE,stderr=log,cwd=Path(__file__).resolve().parents[1],
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),start_new_session=os.name!='nt')
                self.monitor=threading.Thread(target=self._finish,args=(self.process,task_id,work,log),daemon=True)
                self.monitor.start()
            except BaseException as error:
                if self.process:
                    AvatarTasks._terminate(self.process)
                    if self.process.stdout:self.process.stdout.close()
                    self.process=None
                log.close();self.task.update(status='failed',error='视频任务未启动：'+str(error))
                try:self._save()
                except OSError:logging.exception('无法保存视频任务启动失败状态')
                raise
            return dict(self.task)

    def _finish(self,process,task_id,work,log):
        accepted=False
        try:
            output,_=process.communicate(timeout=600)
            response=json.loads(output.decode('utf-8'))
            if process.returncode or response.get('ok') is not True:
                raise ProductError(response.get('error') or '视频工作进程失败')
            result=response['result'];path=Path(result['output']).resolve()
            with self.lock:
                if self.closed or self.task['id']!=task_id or self.task['status']!='running':return
                self._validate(self.task)
                if path!=(work/'output.mp4').resolve() or result['audio_sha256']!=self.task['audio_sha256']:
                    raise ProductError('视频结果路径或输入音频不符')
                if not result.get('full_decode_passed') or digest(path)!=result['output_sha256']:
                    raise ProductError('视频产物校验失败')
                self.task.update(status='succeeded',result=result);self._save();accepted=True
        except Exception as error:
            with self.lock:
                if self.task and self.task['id']==task_id and self.task['status'] in {'running','succeeded'} and not accepted:
                    self.task.update(status='failed',error='视频合成失败或输入已变化，请检查输入后重试')
                    self.task.pop('result',None)
                    try:self._save()
                    except OSError:logging.exception('无法保存视频失败状态')
                    logging.warning('视频任务 %s 失败：%s',task_id,error)
        finally:
            AvatarTasks._terminate(process)
            if process.stdout:process.stdout.close()
            log.close()
            if work.resolve().parent==self.jobs:
                (work/'audio.wav').unlink(missing_ok=True)
                (work/'output_temp.mp4').unlink(missing_ok=True)
                if not accepted:(work/'output.mp4').unlink(missing_ok=True)
            with self.lock:
                if self.process is process:self.process=None

    def video_path(self,task_id):
        with self.lock:
            state=self.state()
            if not state or state['id']!=task_id or state['status']!='succeeded':
                raise Conflict('视频任务未完成或已失效')
            path=Path(state['result']['output']).resolve()
            if path!=(self.jobs/state['id']/'output.mp4').resolve() or not path.is_relative_to(self.jobs):
                raise ProductError('视频文件路径越界')
            try:valid=digest(path)==state['result']['output_sha256']
            except OSError:valid=False
            if not valid:
                self.task.update(status='failed',error='视频文件缺失或已变化，请重新生成')
                self.task.pop('result',None);self._save()
                raise Conflict('视频文件已变化，请重新生成')
            return path

    def cancel(self,task_id):
        with self.lock:
            if not self.task or self.task['id']!=task_id:raise ProductError('视频任务不存在')
            if self.task['status']=='running':
                self.task.update(status='cancelled');self._save()
                if self.process:AvatarTasks._terminate(self.process)
            monitor=self.monitor
        if monitor:monitor.join(timeout=20)
        return self.state()

    def close(self):
        with self.lock:self.closed=True;task_id=self.task['id'] if self.task else None
        if task_id:self.cancel(task_id)
