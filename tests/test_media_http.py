"""Byte transport fixtures, not codec or model acceptance."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from scripts.media_http import range_bounds,serve_file


class MediaTests(unittest.TestCase):
    def test_ranges(self):
        for value,expected in [(None,(0,9,200)),('bytes=2-5',(2,5,206)),('bytes=7-',(7,9,206)),
                               ('bytes=-3',(7,9,206)),('bytes=0-999',(0,9,206)),('bytes=-999',(0,9,206))]:
            self.assertEqual(range_bounds(value,10),expected)
        for value in ['bytes=10-','bytes=5-2','bytes=-0','bytes=-','bytes=0-2,4-8','bytes=bad','bytes='+'1'*129+'-']:
            with self.assertRaises(ValueError):range_bounds(value,10)

    def test_streaming_http_full_partial_and_unsatisfiable(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'transport-fixture.mp4';content=bytes(range(256))*9000;path.write_bytes(content)
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):serve_file(self,path,'video/mp4')
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                for value,expected,status in [(None,content,200),('bytes=3-11',content[3:12],206),
                    ('bytes=-12',content[-12:],206),('bytes=1000000-1100000',content[1000000:1100001],206)]:
                    request=Request(base,headers={} if value is None else {'Range':value})
                    with urlopen(request,timeout=5) as response:
                        self.assertEqual(response.status,status);self.assertEqual(response.read(),expected)
                        self.assertEqual(int(response.headers['Content-Length']),len(expected))
                        self.assertEqual(response.headers['Accept-Ranges'],'bytes')
                with self.assertRaises(HTTPError) as failure:
                    urlopen(Request(base,headers={'Range':'bytes=999999999-'}),timeout=5)
                with failure.exception as response:
                    self.assertEqual(response.status,416)
                    self.assertEqual(response.headers['Content-Range'],'bytes */'+str(len(content)))
                    self.assertEqual(response.read(),b'')
            finally:
                server.shutdown();server.server_close();thread.join(timeout=3)


if __name__=='__main__':unittest.main()
