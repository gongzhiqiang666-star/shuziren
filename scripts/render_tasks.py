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
from scripts.render_profiles import PROFILES,result_matches
from scripts.media_runtime import runtime_python


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
        job=(self.jobs/self.task['id']).resolve()
        if job.parent==self.jobs and job.is_dir():
            snapshot=job/'task.json';temporary=job/'task.tmp'
            temporary.write_text(json.dumps(self.task,ensure_ascii=False),encoding='utf-8');temporary.replace(snapshot)

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

    def _content_inputs(self, session_id, source_task_id, avatar_id):
        source = self.tts.products.live_content_source(session_id, source_task_id)
        if source['facts_review'] != 'version_current' or source.get('segment') is None:
            raise Conflict('商品事实或原口播片段已变化，请核对后再生成')
        if not source.get('content_audio_available'):
            raise Conflict('该口播没有可用的原始音频')
        if self.avatars.selected_id() != avatar_id:
            raise Conflict('请先选用该形象')
        avatar = self.avatars.get(avatar_id)
        audio_path = self.tts.products.live_content_audio_path(session_id, source_task_id)
        content = audio_path.read_bytes()
        binding = {
            'source_kind': 'live_content', 'content_session_id': session_id,
            'content_task_id': source_task_id, 'avatar_id': avatar_id,
            'avatar_manifest_sha256': avatar['manifest_sha256'],
            'audio_sha256': hashlib.sha256(content).hexdigest(),
            'product_id': source['product_id'], 'product_version': source['product_version'],
            'script_id': source['script_id'], 'voice_id': source.get('voice_id'),
        }
        audio = {'product_title': source['product_snapshot']['title'], 'speed': 1.0,
                 'caption': source['segment']['content']}
        return binding, content, audio, avatar

    def _task_inputs(self, task):
        if task.get('source_kind') == 'live_content':
            return self._content_inputs(task['content_session_id'], task['content_task_id'], task['avatar_id'])
        return self._inputs(task['tts_task_id'], task['avatar_id'])

    def _validate(self,task):
        if task['status']=='succeeded' and not result_matches(task.get('render_profile','standard'),task.get('result',{}),allow_legacy='render_profile' not in task):
            raise Conflict('视频生成方案与结果不符，请重新生成')
        if task['status']=='succeeded' and task.get('result',{}).get('audio_complete') is not True:
            raise Conflict('旧视频未通过新版音轨完整性检查，请重新生成')
        binding,_,_,_=self._task_inputs(task)
        if any(task.get(key)!=value for key,value in binding.items()):
            raise Conflict('视频输入已变化，请重新生成')

    def state(self):
        with self.lock:
            if self.task and self.task['status'] in {'running','succeeded'}:
                try:self._validate(self.task)
                except (ProductError, ValueError, OSError):
                    self.task.update(status='failed',error='商品、语音或形象已变化，本次视频已失效')
                    self.task['previous_result']=self.task.pop('result',None);self._save()
                    if self.process:AvatarTasks._terminate(self.process)
            return dict(self.task) if self.task else None

    def start(self,tts_task_id,avatar_id,render_profile='standard'):
        if not isinstance(render_profile,str) or render_profile not in PROFILES:raise ProductError('视频生成方案无效')
        if not all(isinstance(value,str) for value in (tts_task_id,avatar_id)):
            raise ProductError('语音任务或形象ID无效')
        with self.lock:
            if self.closed:raise Conflict('视频合成服务正在退出')
            if self.process is not None or (self.monitor and self.monitor.is_alive()):
                raise Conflict('已有视频合成任务，请等待或取消')
            binding,content,audio,avatar=self._inputs(tts_task_id,avatar_id)
            return self._start(binding, content, audio, avatar, render_profile)

    def start_content(self, session_id, task_id, avatar_id, render_profile='standard'):
        if not isinstance(render_profile, str) or render_profile not in PROFILES:
            raise ProductError('视频生成方案无效')
        if not all(isinstance(value, str) and value for value in (session_id, task_id, avatar_id)):
            raise ProductError('口播记录或形象ID无效')
        with self.lock:
            if self.closed: raise Conflict('视频合成服务正在退出')
            if self.process is not None or (self.monitor and self.monitor.is_alive()):
                raise Conflict('已有视频合成任务，请等待或取消')
            binding, content, audio, avatar = self._content_inputs(session_id, task_id, avatar_id)
            return self._start(binding, content, audio, avatar, render_profile)

    def _start(self, binding, content, audio, avatar, render_profile):
            python=runtime_python(self.runtime)
            if not python.is_file():raise ProductError('缺少视频合成运行解释器')
            task_id=str(uuid.uuid4());work=self.jobs/task_id;work.mkdir()
            self.task={'id':task_id,'status':'running',**binding,'product_title':audio['product_title'],
                       'avatar_name':avatar['name'],'speed':audio['speed'],'render_profile':render_profile}
            if 'caption' in audio: self.task['caption'] = audio['caption']
            log=(work/'worker.log').open('wb')
            try:
                (work/'audio.wav').write_bytes(content);self._save()
                self.process=subprocess.Popen([str(python),'-X','utf8','-m','scripts.render_worker',
                    '--runtime-root',str(self.runtime),'--avatar-directory',str(self.avatars._directory(binding['avatar_id'])),
                    '--audio',str(work/'audio.wav'),'--output',str(work/'output.mp4'),
                    '--render-profile',render_profile,'--engine-cache',str(self.data/'render-engine-cache')],
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
                if not result_matches(self.task.get('render_profile','standard'),result,allow_legacy='render_profile' not in self.task):raise ProductError('视频工作进程返回了其他生成方案')
                if path!=(work/'output.mp4').resolve() or result['audio_sha256']!=self.task['audio_sha256']:
                    raise ProductError('视频结果路径或输入音频不符')
                if not result.get('full_decode_passed') or result.get('audio_complete') is not True or digest(path)!=result['output_sha256']:
                    raise ProductError('视频产物校验失败')
                if self.task.get('source_kind') == 'live_content':
                    published = self._burn_live_content(work, result)
                    result.update(published_output=published['output'],
                                  published_output_sha256=published['output_sha256'],
                                  published_full_decode_passed=published['full_decode_passed'],
                                  subtitles_burned=True)
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
                if not accepted:
                    (work/'output.mp4').unlink(missing_ok=True)
                    (work/'published.mp4').unlink(missing_ok=True)
            with self.lock:
                if self.process is process:self.process=None

    def video_path(self,task_id):
        with self.lock:
            state=self.state()
            if not state or state['id']!=task_id or state['status']!='succeeded':
                raise Conflict('视频任务未完成或已失效')
            published = state['result'].get('published_output')
            path=Path(published or state['result']['output']).resolve()
            expected = self.jobs/state['id']/('published.mp4' if published else 'output.mp4')
            if path!=expected.resolve() or not path.is_relative_to(self.jobs):
                raise ProductError('视频文件路径越界')
            expected_hash = state['result'].get('published_output_sha256', state['result']['output_sha256'])
            try:valid=digest(path)==expected_hash
            except OSError:valid=False
            if not valid:
                self.task.update(status='failed',error='视频文件缺失或已变化，请重新生成')
                self.task.pop('result',None);self._save()
                raise Conflict('视频文件已变化，请重新生成')
            return path

    @staticmethod
    def _subtitle_text(caption, samples):
        if not isinstance(caption, str) or not caption.strip() or type(samples) is not int or samples <= 0:
            raise Conflict('该视频缺少字幕所需的话术或采样数')
        seconds, fraction = divmod((samples + 23) // 24, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        caption = '\n'.join(line for line in caption.splitlines() if line.strip())
        return f'1\n00:00:00,000 --> {hours:02}:{minutes:02}:{seconds:02},{fraction:03}\n{caption}\n'

    def _burn_live_content(self, work, result):
        subtitle = work/'subtitle.srt'
        subtitle.write_text(self._subtitle_text(self.task.get('caption'), result.get('input_audio_samples')),
                            encoding='utf-8')
        output = (work/'published.mp4').resolve()
        python = runtime_python(self.runtime)
        completed = subprocess.run([str(python), '-X', 'utf8', '-m', 'scripts.subtitle_burn_worker',
            '--runtime-root', str(self.runtime), '--video', result['output'], '--subtitle', str(subtitle),
            '--audio', str(work/'audio.wav'), '--output', str(output)], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, timeout=300, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try: response = json.loads(completed.stdout.decode('utf-8'))
        except (UnicodeDecodeError, ValueError): raise ProductError('字幕烧录工作进程返回无效') from None
        published = response.get('result', {})
        if (completed.returncode or response.get('ok') is not True or Path(published.get('output', '')).resolve() != output
                or published.get('audio_complete') is not True or published.get('full_decode_passed') is not True
                or not output.is_file() or digest(output) != published.get('output_sha256')):
            raise ProductError('字幕烧录成片校验失败')
        return published

    def subtitle(self, task_id):
        with self.lock:
            self.video_path(task_id)
            task = self.task
            if task.get('source_kind') == 'live_content':
                caption = task.get('caption')
                script = {'text': caption} if isinstance(caption, str) and caption.strip() else None
            else:
                audio = self.tts.state()
                if not audio or audio['id'] != task['tts_task_id'] or audio.get('kind'):
                    raise Conflict('该视频缺少可核对的完整话术来源')
                script = next((row for row in self.tts.products.scripts(task['product_id'])
                               if row['id'] == task['script_id']), None)
            return self._subtitle_text(script['text'] if script else None,
                                       task['result'].get('input_audio_samples'))

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
