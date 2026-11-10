from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from scripts.console_llm import LLMError, environment_config, generate
from scripts.console_comment_reply import generate_reply
from scripts.product_store import ProductStore, Conflict
from scripts.llm_tasks import LLMTasks


class ConsoleLLMTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ProductStore(self.temp.name)
        self.product = self.store.save(title='茶杯', content='容量300毫升', product_index='008')
        self.responses = [(200, '这款茶杯容量为300毫升，请按自己的需要选择。')]
        self.requests = []
        self.on_request = None
        test = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                test.requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                if test.on_request: test.on_request()
                status, content = test.responses.pop(0) if len(test.responses)>1 else test.responses[0]
                try:
                    self.send_response(status)
                    self.send_header('Content-Type','application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'choices':[{'message':{'content':content}}]}).encode())
                except OSError: pass  # Client intentionally disconnected in timeout cases.
        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop)
        self.config = environment_config({'SHUZIREN_LLM_ENDPOINT':'http://127.0.0.1:%s/chat/completions'%self.server.server_port,
                                          'SHUZIREN_LLM_API_KEY':'test-secret-sentinel','SHUZIREN_LLM_MODEL':'protocol-test'})

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)

    def run_generation(self, **options):
        return generate(self.store,self.product['id'],self.product['version'],config=self.config,**options)

    def test_explicit_http_transport_and_product_binding(self):
        result = self.run_generation()
        self.assertEqual(result['product_id'],self.product['id'])
        saved = self.store.scripts(self.product['id'])
        self.assertEqual(saved[0]['source'],'llm')
        self.assertIn('300毫升',self.requests[0]['messages'][-1]['content'])

    def test_empty_and_authorization_failures_do_not_save_or_leak(self):
        for status, content in [(200,''),(401,'test-secret-sentinel'),(500,'test-secret-sentinel')]:
            self.responses = [(status,content)]
            with self.assertRaises(LLMError) as caught: self.run_generation()
            self.assertNotIn('test-secret-sentinel',str(caught.exception))
            self.assertEqual(self.store.scripts(self.product['id']),[])

    def test_timeout_rejected_without_script(self):
        self.config['timeout'] = .01
        self.on_request = lambda: time.sleep(.05)
        with self.assertRaises(LLMError): self.run_generation()
        self.assertEqual(self.store.scripts(self.product['id']),[])

    def test_comment_reply_recovers_after_timeout_and_service_unavailable(self):
        self.config['timeout'] = .01
        self.on_request = lambda: time.sleep(.08)
        with self.assertRaises(LLMError):
            generate_reply(self.product, '容量多少？', self.config)
        self.on_request = None
        self.config['timeout'] = 2
        self.responses = [(503, 'unavailable')]
        with self.assertRaises(LLMError):
            generate_reply(self.product, '容量多少？', self.config)
        self.responses = [(200, '这款茶杯容量为300毫升。')]
        self.assertEqual(generate_reply(self.product, '容量多少？', self.config), self.responses[0][1])
        self.assertEqual(self.store.scripts(self.product['id']), [])

    def test_language_retry_uses_explicit_config(self):
        self.responses = [(200,'中文不应出现在英文输出'),(200,'This ceramic cup holds three hundred millilitres.')]
        result = self.run_generation(instructions='[TARGET_LANGUAGE=en]')
        self.assertIn('This ceramic',result['text'])
        self.assertEqual(len(self.requests),2)

    def test_changed_product_rejects_completed_result(self):
        def edit():
            p=self.store.get(self.product['id'])
            self.store.save(title=p['title'],content='容量500毫升',product_index=p['product_index'],
                            product_id=p['id'],version=p['version'])
        self.on_request=edit
        with self.assertRaises(Conflict): self.run_generation()
        self.assertEqual(self.store.scripts(self.product['id']),[])

    def test_missing_and_invalid_config_do_not_read_legacy(self):
        with self.assertRaises(LLMError): environment_config({})
        for endpoint in ['http://example.com/chat','https://user:secret@example.com/chat','https://example.com/chat?key=secret']:
            with self.assertRaises(LLMError):
                environment_config({'SHUZIREN_LLM_ENDPOINT':endpoint,'SHUZIREN_LLM_MODEL':'x','SHUZIREN_LLM_API_KEY':'x'})

    def tasks(self):
        env = {'SHUZIREN_LLM_ENDPOINT':self.config['endpoint'], 'SHUZIREN_LLM_API_KEY':self.config['api_key'],
               'SHUZIREN_LLM_MODEL':self.config['model']}
        environment_patch=patch.dict(os.environ,env)
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        tasks=LLMTasks(self.store)
        self.addCleanup(tasks.close)
        return tasks

    def wait_task(self,tasks):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            state=tasks.state()
            if state['status']!='running': return state
            time.sleep(.05)
        self.fail('Worker did not finish within 15 seconds')

    def test_spawn_task_success_duplicate_and_persisted_status(self):
        tasks=self.tasks()
        task=tasks.start(self.product['id'],1)
        with self.assertRaises(Conflict): tasks.start(self.product['id'],1)
        state=self.wait_task(tasks)
        self.assertEqual(state['status'],'succeeded',state)
        self.assertEqual(len(self.store.scripts(self.product['id'])),1)
        tasks.close()
        self.assertEqual(LLMTasks(self.store).state()['id'],task['id'])
        self.assertNotIn('test-secret-sentinel',tasks.path.read_text())

    def test_cancel_terminates_owned_process_and_prevents_commit(self):
        entered=threading.Event()
        def delay(): entered.set(); time.sleep(1)
        self.on_request=delay
        tasks=self.tasks()
        task=tasks.start(self.product['id'],1)
        self.assertTrue(entered.wait(timeout=10))
        self.assertEqual(tasks.cancel(task['id'])['status'],'cancelled')
        self.assertFalse(tasks.process.is_alive())
        self.assertEqual(self.store.scripts(self.product['id']),[])

    def test_close_cancels_and_restart_marks_unfinished(self):
        self.on_request=lambda: time.sleep(1)
        tasks=self.tasks()
        tasks.start(self.product['id'],1)
        tasks.close()
        self.assertFalse(tasks.process.is_alive())
        self.assertEqual(tasks.state()['status'],'cancelled')
        tasks.path.write_text(json.dumps({'id':'old','status':'running'}))
        reopened=LLMTasks(self.store)
        self.assertEqual(reopened.state()['status'],'interrupted')


if __name__ == '__main__': unittest.main()
