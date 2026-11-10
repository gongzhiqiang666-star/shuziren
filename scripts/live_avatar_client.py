"""Own persistent avatar worker, bounded control messages and cancellable process tree."""
import json
from pathlib import Path
import queue
import subprocess
import threading

from scripts.avatar_tasks import AvatarTasks
from scripts.avatar_store import digest
from scripts.media_runtime import runtime_python


class LiveAvatarClient:
    def __init__(self,runtime,avatar,data_directory,cache=None):
        runtime=Path(runtime).resolve();avatar=Path(avatar).resolve();data=Path(data_directory).resolve();data.mkdir(parents=True,exist_ok=True)
        self.log=(data/'live-avatar-worker.log').open('ab');self.closed=False;self.busy=False;self.reader=None
        self.calls=threading.Lock();self.guard=threading.RLock()
        try:
            self.process=subprocess.Popen([str(runtime_python(runtime)),'-X','utf8','-m','scripts.live_avatar_worker',
                '--runtime-root',str(runtime),'--avatar-directory',str(avatar),'--engine-cache',str(Path(cache).resolve() if cache else data/'live-avatar-cache')],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True,encoding='utf-8',bufsize=1,
                cwd=Path(__file__).resolve().parents[1],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except BaseException:self.log.close();raise

    def request(self,operation,timeout=360,progress=None,**values):
        with self.calls:
            with self.guard:
                if self.closed:raise RuntimeError('Avatar worker is closed')
                self.busy=True
            result=queue.Queue(maxsize=1)
            def read():
                try:
                    while True:
                        line=self.process.stdout.readline(1048577)
                        if not line:raise RuntimeError('Avatar worker exited before responding')
                        if len(line)>1048576:raise ValueError('Oversized worker message')
                        value=json.loads(line)
                        if 'event' in value:
                            if progress:progress(value)
                        else:result.put(value);return
                except BaseException as error:result.put(error)
            try:
                self.process.stdin.write(json.dumps({'operation':operation,**values},ensure_ascii=False)+'\n');self.process.stdin.flush()
                self.reader=threading.Thread(target=read,name='live-avatar-control',daemon=True);self.reader.start()
                try:response=result.get(timeout=timeout)
                except queue.Empty:
                    self.close();raise TimeoutError('Avatar worker timed out; owned process tree stopped')
                if isinstance(response,BaseException):raise response
                # A final response means the worker has finished this request.
                # Close it via EOF on a validation error rather than force-killing
                # an idle process whose Windows log handle is still closing.
                if isinstance(response,dict) and 'ok' in response:
                    with self.guard:self.busy=False
                if self.closed:raise RuntimeError('Stopped avatar result cannot be accepted')
                if response.get('ok') is not True:raise RuntimeError(str(response))
                value=response['result']
                if operation in {'render','stream','idle'}:
                    if any(value.get(key)!=values.get(key) for key in ['session_id','task_id','pcm_sha256']):raise ValueError('Avatar response binding mismatch')
                    if operation!='idle' and digest(values['audio'])!=value['audio_sha256']:raise ValueError('Avatar audio fingerprint mismatch')
                    if operation=='render':
                        if Path(value['output']).resolve()!=Path(values['output']).resolve():raise ValueError('Avatar output path mismatch')
                        if digest(value['output'])!=value['output_sha256']:raise ValueError('Avatar media fingerprint mismatch')
                    elif value.get('output_mode')!='raw-frame-stream' or value.get('raw_frames_sent')!=value.get('frames'):raise ValueError('Avatar raw stream result mismatch')
                    if value.get('timing')!=values.get('timing'):raise ValueError('Avatar timing response mismatch')
                with self.guard:
                    if self.closed:raise RuntimeError('Stopped avatar result cannot be accepted')
                    return value
            except BaseException:
                self.close();raise
            finally:
                with self.guard:self.busy=False

    def close(self):
        with self.guard:
            if self.closed:return
            self.closed=True;busy=self.busy
        try:
            if busy:AvatarTasks._terminate(self.process)
            else:
                try:self.process.stdin.close();self.process.wait(timeout=10)
                except (OSError,subprocess.TimeoutExpired):AvatarTasks._terminate(self.process)
        finally:
            if self.reader and self.reader is not threading.current_thread():self.reader.join(timeout=5)
            for pipe in [self.process.stdin,self.process.stdout]:
                if pipe and not pipe.closed:
                    try:pipe.close()
                    except (OSError,ValueError):pass
            self.log.close()
