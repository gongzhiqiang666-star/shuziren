"""One owned video-preparation process, bounded lifetime and parent-only import."""
import json
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import uuid
import psutil

from scripts.avatar_store import AvatarStore, AvatarError, digest
from scripts.product_store import Conflict


class AvatarTasks:
    def __init__(self, runtime_root, data_directory):
        self.runtime = Path(runtime_root).resolve()
        self.data = Path(data_directory).resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.jobs = self.data/'avatar-jobs'
        self.jobs.mkdir(exist_ok=True)
        self.path = self.data/'avatar-task.json'
        self.lock = threading.RLock()
        self.process = self.monitor = None
        self.closed = False
        self.task = None
        if self.path.exists():
            self.task = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.task, dict) or self.task.get('status') not in {
                'running', 'succeeded', 'failed', 'cancelled', 'interrupted'}:
                raise AvatarError('形象制作任务记录损坏')
            if self.task['status']=='running':
                self.task.update(status='interrupted', error='服务曾中断，请重新制作')
                self._save()

    def _save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.task, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.path)

    def state(self):
        with self.lock:
            value = dict(self.task) if self.task else None
            if value and value['status']=='running':
                try:
                    value['phase'] = json.loads((self.jobs/value['id']/'progress.json').read_text())['phase']
                except (OSError, ValueError, KeyError):
                    value['phase'] = 'starting'
            return value

    def start(self, source, name, resolution='720p'):
        if not isinstance(source, str) or not Path(source).is_absolute():
            raise AvatarError('请选择本机视频的绝对路径')
        source = Path(source).resolve(strict=True)
        if not source.is_file() or source.stat().st_size > 2*1024**3:
            raise AvatarError('当前视频制作支持不超过2GiB的文件')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise AvatarError('形象名称须为1至100字')
        if not isinstance(resolution,str) or resolution not in {'480p','720p','1080p','2k','4k'}:
            raise AvatarError('形象清晰度无效')
        with self.lock:
            if self.closed:
                raise AvatarError('形象制作服务正在退出')
            if self.process is not None or (self.monitor and self.monitor.is_alive()):
                raise Conflict('已有形象制作任务，请等待完成或取消')
            task_id = str(uuid.uuid4())
            work = self.jobs/task_id
            work.mkdir()
            task = {'id':task_id, 'status':'running', 'name':name.strip(), 'source':str(source),
                    'source_sha256':digest(source), 'resolution':resolution}
            python = self.runtime/'_internal/env/python.exe'
            if not python.is_file():
                raise AvatarError('缺少形象制作运行解释器')
            log = (work/'worker.log').open('wb')
            try:
                self.task = task
                self._save()
                self.process = subprocess.Popen([str(python), '-X', 'utf8', '-m', 'scripts.avatar_prepare_worker',
                    '--runtime-root', str(self.runtime), '--source', str(source),
                    '--output', str(work/'prepared'), '--resolution', resolution],
                    stdout=subprocess.PIPE, stderr=log, cwd=str(Path(__file__).resolve().parents[1]),
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=os.name!='nt')
                self.monitor = threading.Thread(target=self._finish, args=(self.process, task_id, work, log), daemon=True)
                self.monitor.start()
            except BaseException as error:
                if self.process is not None:
                    self._terminate(self.process)
                    if self.process.stdout:
                        self.process.stdout.close()
                    self.process = None
                log.close()
                self.task.update(status='failed',error='制作任务未启动：'+str(error))
                try:
                    self._save()
                except OSError:
                    logging.exception('无法保存形象制作启动失败状态')
                raise
            return dict(task)

    @staticmethod
    def _terminate(process):
        if process.poll() is not None:
            return
        try:
            children = psutil.Process(process.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            children = []
        if os.name=='nt':
            # Only the live Popen process created by this manager and its children.
            try:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               capture_output=True, timeout=15,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except subprocess.TimeoutExpired:
                logging.warning('制作进程树终止超时，回收已捕获的自有子进程')
        else:
            os.killpg(process.pid, signal.SIGKILL)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        # TerminateProcess/taskkill can return before descendant handles are released.
        _, alive = psutil.wait_procs(children, timeout=5)
        for child in alive:
            try:
                child.kill()  # psutil checks process creation identity before signalling.
            except psutil.NoSuchProcess:
                pass
        if alive and psutil.wait_procs(alive, timeout=5)[1]:
            raise AvatarError('制作子进程未能结束，详细信息已记录')

    def _finish(self, process, task_id, work, log):
        try:
            output, _ = process.communicate(timeout=600)
            response = json.loads(output.decode('utf-8'))
            if process.returncode or response.get('ok') is not True:
                raise AvatarError(response.get('error') or '制作工作进程失败')
            with self.lock:
                if self.closed or self.task['id']!=task_id or self.task['status']!='running':
                    return
                expected = work/'prepared'
                if Path(response['result']['prepared_directory']).resolve()!=expected.resolve():
                    raise AvatarError('制作结果目录无效')
                if (response['result']['source_sha256']!=self.task['source_sha256']
                    or digest(self.task['source'])!=self.task['source_sha256']):
                    raise AvatarError('源视频在制作中已变化，结果未导入')
                avatar = AvatarStore(self.data).import_prepared(expected, self.task['name'])
                self.task.update(status='succeeded', result={'avatar':avatar})
                self._save()
        except Exception as error:
            with self.lock:
                if self.task and self.task['id']==task_id and self.task['status']=='running':
                    self.task.update(status='failed', error=str(error))
                    self._save()
        finally:
            self._terminate(process)
            if process.stdout:
                process.stdout.close()
            log.close()
            prepared = work/'prepared'
            if prepared.exists() and prepared.resolve().parent==work.resolve() and work.resolve().parent==self.jobs:
                shutil.rmtree(prepared)
            with self.lock:
                if self.process is process:
                    self.process = None

    def cancel(self, task_id):
        with self.lock:
            if not self.task or self.task['id']!=task_id:
                raise AvatarError('形象制作任务不存在')
            if self.task['status']=='running':
                self.task.update(status='cancelled')
                self._save()
                if self.process:
                    self._terminate(self.process)
            monitor = self.monitor
            result = dict(self.task)
        if monitor:
            monitor.join(timeout=20)
        return result

    def close(self):
        with self.lock:
            self.closed = True
            task_id = self.task['id'] if self.task else None
        if task_id:
            self.cancel(task_id)
