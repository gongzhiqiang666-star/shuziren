"""Manual UI protocol fixture, NOT a model. Run from repository root with -m."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time


def main():
    parser=argparse.ArgumentParser(description='仅供控制台协议验收，不提供真实模型推理')
    parser.add_argument('--data-directory',required=True,type=Path)
    parser.add_argument('--port',type=int,default=5188)
    args=parser.parse_args()
    args.data_directory.mkdir(parents=True,exist_ok=True)
    mode_path=args.data_directory/'fixture-mode.txt'
    if not mode_path.exists(): mode_path.write_text('slow',encoding='utf-8')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            mode=mode_path.read_text(encoding='utf-8-sig').strip()
            if mode=='slow': time.sleep(20)
            answer='【协议测试文本，非模型生成】商品信息仅用于控制台任务验证。'
            if mode=='empty': answer=''
            try:
                self.send_response(401 if mode=='unauthorized' else 200)
                self.send_header('Content-Type','application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'choices':[{'message':{'content':answer}}]}).encode())
            except OSError: pass
    fixture=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    fixture.daemon_threads=True
    threading.Thread(target=fixture.serve_forever,daemon=True).start()
    os.environ.update(SHUZIREN_LLM_ENDPOINT='http://127.0.0.1:%s/chat/completions'%fixture.server_port,
                      SHUZIREN_LLM_MODEL='protocol-fixture-not-a-model',SHUZIREN_LLM_API_KEY='fixture-not-a-secret')
    print('PROTOCOL FIXTURE ONLY; modes: slow / success / empty / unauthorized',flush=True)
    from scripts.local_console import main as console_main
    try:
        return console_main(['--data-directory',str(args.data_directory),'--port',str(args.port)])
    finally:
        fixture.shutdown();fixture.server_close()


if __name__=='__main__': raise SystemExit(main())
