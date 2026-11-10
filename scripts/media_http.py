"""Bounded streaming and byte ranges for validated local media files."""
import logging
import re


def range_bounds(value,size):
    if size<=0:raise ValueError('Empty media')
    if value is None:return 0,size-1,200
    if len(value)>128:raise ValueError('Invalid range')
    match=re.fullmatch(r'bytes=([0-9]*)-([0-9]*)',value.strip())
    if not match or not any(match.groups()):raise ValueError('Invalid range')
    left,right=match.groups()
    if not left:
        count=int(right)
        if not count:raise ValueError('Invalid suffix')
        return max(0,size-count),size-1,206
    start=int(left);end=min(int(right),size-1) if right else size-1
    if start>=size or end<start:raise ValueError('Unsatisfiable range')
    return start,end,206


def serve_file(handler,path,content_type):
    with path.open('rb') as stream:
        size=path.stat().st_size
        try:
            start,end,status=range_bounds(handler.headers.get('Range'),size)
        except ValueError:
            handler.send_response(416)
            handler.send_header('Content-Range',f'bytes */{size}')
            handler.send_header('Content-Length','0')
            handler.end_headers()
            return
        try:
            handler.send_response(status)
            handler.send_header('Content-Type',content_type)
            handler.send_header('Content-Length',str(end-start+1))
            handler.send_header('Accept-Ranges','bytes')
            handler.send_header('Cache-Control','no-store')
            handler.send_header('X-Content-Type-Options','nosniff')
            if status==206:handler.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            handler.end_headers();stream.seek(start);remaining=end-start+1
            while remaining:
                block=stream.read(min(remaining,1024*1024))
                if not block:raise OSError('媒体文件在传输中发生变化')
                handler.wfile.write(block);remaining-=len(block)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            logging.info('媒体预览客户端已断开')
        except OSError:
            handler.close_connection=True
            logging.exception('媒体传输失败，已关闭当前连接')
