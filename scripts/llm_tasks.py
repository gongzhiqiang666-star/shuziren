"""One owned LLM worker; only the parent can commit a result."""
import json
import multiprocessing
import sqlite3
import threading
import time
import uuid

from scripts.console_llm import environment_config
from scripts.product_store import Conflict, ProductError, product_prompt_info


def _worker(connection, snapshot, instructions, config):
    try:
        from recovered.generate_structured_speech import generate_structured_speech_with_config
        prompt_info = product_prompt_info(snapshot)
        result = generate_structured_speech_with_config(
            prompt_info, instructions, llm_config=config)
        connection.send({'text': result, 'prompt_info': prompt_info})
    except Exception:
        connection.send({'error': '生成失败，请检查服务授权、超时和模型返回后重试'})
    finally:
        connection.close()


class LLMTasks:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.process = self.connection = self.monitor = None
        self.closed = False
        self.path = store.path.parent / 'llm-task.json'
        self.task = None
        if self.path.exists():
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(value, dict) or value.get('status') not in {'running','succeeded','failed','cancelled','interrupted'}:
                raise ProductError('生成任务记录损坏，请保留文件并检查')
            self.task = value
            if value['status'] == 'running':
                self.task['status'] = 'interrupted'
                self.task['error'] = '上次服务已中断，请确认后重新生成'
                self._save()

    def _save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.task, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.path)

    def state(self):
        with self.lock:
            return dict(self.task) if self.task else None

    def start(self, product_id, version, instructions=''):
        if type(version) is not int or not isinstance(instructions,str) or len(instructions)>10000:
            raise ProductError('生成版本或要求无效')
        with self.lock:
            if self.closed: raise Conflict('服务正在退出')
            if self.task and self.task['status']=='running': raise Conflict('已有生成任务，请等待或取消')
            snapshot = self.store.get(product_id)
            if snapshot['version'] != version: raise Conflict('商品已修改，请重新读取')
            config = environment_config()
            context = multiprocessing.get_context('spawn')
            parent, child = context.Pipe(duplex=False)
            process = context.Process(target=_worker,args=(child,snapshot,instructions,config),daemon=True)
            self.task = {'id':str(uuid.uuid4()),'product_id':product_id,'product_title':snapshot['title'],'product_version':version,'status':'running'}
            self._save()
            try:
                process.start()
            except Exception:
                child.close(); parent.close()
                self.task.update(status='failed',error='无法启动生成工作进程')
                self._save()
                raise ProductError('无法启动生成工作进程') from None
            child.close()
            self.process, self.connection = process,parent
            self.monitor = threading.Thread(target=self._watch,args=(process,parent,snapshot),daemon=True)
            self.monitor.start()
            return dict(self.task)

    def _watch(self, process, connection, snapshot):
        deadline = time.monotonic()+250  # Existing language retry can issue four bounded requests.
        message = None
        try:
            while time.monotonic()<deadline:
                if connection.poll(.1):
                    message=connection.recv(); break
                with self.lock:
                    if self.closed or self.task['status']!='running': return
                if not process.is_alive(): break
            with self.lock:
                if self.closed or self.task['status']!='running': return
                try:
                    if not message or 'text' not in message: raise ProductError('生成失败或超时，请检查服务后重试')
                    script_id=self.store.add_script(snapshot,message['text'],source='llm',
                                                    expected_prompt_info=message.get('prompt_info'))
                    self.task.update(status='succeeded',script_id=script_id)
                except (ProductError, OSError, sqlite3.Error):
                    self.task.update(status='failed',error='生成失败或商品已修改；未保存新话术，请重新读取后重试')
                self._save()
        except (EOFError, OSError):
            with self.lock:
                if self.task['status']=='running':
                    self.task.update(status='failed',error='生成工作进程中断，请重试'); self._save()
        finally:
            if process.is_alive(): process.terminate()
            process.join(timeout=3)
            connection.close()

    def cancel(self, task_id):
        with self.lock:
            if not self.task or self.task['id']!=task_id: raise ProductError('生成任务不存在')
            if self.task['status']=='running':
                self.task['status']='cancelled'; self._save()
                if self.process and self.process.is_alive(): self.process.terminate()
            result=dict(self.task)
            monitor=self.monitor
        if monitor: monitor.join(timeout=5)
        return result

    def close(self):
        with self.lock:
            self.closed=True
            task_id=self.task['id'] if self.task else None
        if task_id: self.cancel(task_id)
