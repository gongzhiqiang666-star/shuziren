"""Authenticated loopback raw BGR frames with bounded consumer credits."""
from dataclasses import dataclass
import hmac
import json
import queue
import secrets
import socket
import struct
import threading
import numpy as np


@dataclass(frozen=True)
class LiveFrame:
    session_id:str
    task_id:str
    frame_index:int
    image:np.ndarray


def read_exact(connection,size,allow_eof=False):
    blocks=[];remaining=size
    while remaining:
        try:block=connection.recv(min(remaining,1048576))
        except socket.timeout:
            if allow_eof and remaining==size:continue  # Idle between utterances is valid.
            raise
        if not block:
            if allow_eof and remaining==size:return None
            raise ConnectionError('Frame stream ended inside a packet')
        blocks.append(block);remaining-=len(block)
    return b''.join(blocks)


class FrameReceiver:
    def __init__(self,session_id,width,height,capacity=8):
        if not isinstance(session_id,str) or not session_id or any(type(v) is not int or v<1 for v in [width,height,capacity]) or capacity>8 or width*height*3>33554432:
            raise ValueError('Invalid bounded frame channel configuration')
        self.session_id=session_id;self.width=width;self.height=height;self.capacity=capacity
        self.token=secrets.token_bytes(32);self.frames=queue.Queue(maxsize=capacity);self.stop=threading.Event()
        self.error=None;self.connection=None;self.received=0;self.peak=0;self.full=threading.Event()
        self.listener=socket.socket();self.listener.bind(('127.0.0.1',0));self.listener.listen(1);self.listener.settimeout(.2)
        self.port=self.listener.getsockname()[1]
        self.thread=threading.Thread(target=self._read,name='live-frame-receiver',daemon=True);self.thread.start()

    def descriptor(self):return {'port':self.port,'token':self.token.hex(),'width':self.width,'height':self.height,'capacity':self.capacity}

    def _read(self):
        try:
            while not self.stop.is_set():
                try:self.connection,_=self.listener.accept();break
                except socket.timeout:continue
            if self.stop.is_set():return
            connection=self.connection;connection.settimeout(30)
            connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            if not hmac.compare_digest(read_exact(connection,32),self.token):raise PermissionError('Unauthorized frame connection')
            self.listener.close()
            while not self.stop.is_set():
                prefix=read_exact(connection,4,allow_eof=True)
                if prefix is None:break
                size=struct.unpack('!I',prefix)[0]
                if not 1<=size<=4096:raise ValueError('Invalid frame header length')
                metadata=json.loads(read_exact(connection,size))
                if metadata.get('session_id')!=self.session_id or type(metadata.get('frame_index')) is not int or metadata['frame_index']!=self.received:
                    raise ValueError('Stale, missing or repeated frame')
                if metadata.get('width')!=self.width or metadata.get('height')!=self.height or not isinstance(metadata.get('task_id'),str) or not 1<=len(metadata['task_id'])<=128:
                    raise ValueError('Invalid frame metadata')
                pixels=read_exact(connection,self.width*self.height*3)
                frame=LiveFrame(self.session_id,metadata['task_id'],metadata['frame_index'],np.frombuffer(pixels,dtype=np.uint8).reshape(self.height,self.width,3))
                while not self.stop.is_set():
                    try:self.frames.put(frame,timeout=.05);break
                    except queue.Full:continue
                self.received+=1;self.peak=max(self.peak,self.frames.qsize())
                if self.frames.qsize()==self.capacity:self.full.set()
        except Exception as error:
            if not self.stop.is_set():self.error=error
        finally:
            while not self.stop.is_set():
                try:self.frames.put(None,timeout=.05);break
                except queue.Full:continue

    def take(self,timeout=1):
        if self.stop.is_set():raise RuntimeError('Frame channel stopped')
        if self.error:raise self.error
        value=self.frames.get(timeout=timeout)
        if self.stop.is_set():raise RuntimeError('Frame channel stopped')
        if self.error:raise self.error
        if value is None:
            if self.error:raise self.error
            raise EOFError('Frame stream completed')
        # Credits are returned only when a frame leaves the bounded queue.
        self.connection.sendall(b'1')
        return value

    def close(self):
        self.stop.set()
        for connection in [self.connection,self.listener]:
            if connection:
                try:connection.shutdown(socket.SHUT_RDWR)
                except OSError:pass
                connection.close()
        while True:
            try:self.frames.get_nowait()
            except queue.Empty:break
        try:self.frames.put_nowait(None)
        except queue.Full:pass
        self.thread.join(timeout=2)
        if self.thread.is_alive():raise RuntimeError('Frame receiver did not stop')


class FrameSender:
    def __init__(self,descriptor):
        if set(descriptor)!={'port','token','width','height','capacity'}:raise ValueError('Invalid frame channel descriptor')
        if type(descriptor['port']) is not int or not 1<=descriptor['port']<=65535 or type(descriptor['capacity']) is not int or not 1<=descriptor['capacity']<=8:raise ValueError('Invalid frame channel endpoint')
        self.width=descriptor['width'];self.height=descriptor['height'];self.capacity=descriptor['capacity'];self.credits=self.capacity
        token=bytes.fromhex(descriptor['token'])
        if len(token)!=32:raise ValueError('Invalid frame channel token')
        self.connection=socket.create_connection(('127.0.0.1',descriptor['port']),timeout=30)
        self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        self.connection.sendall(token)

    def send(self,session_id,task_id,frame_index,image):
        if image.shape!=(self.height,self.width,3) or image.dtype!=np.uint8:raise ValueError('Raw frame shape/type mismatch')
        if not self.credits:
            acknowledgements=self.connection.recv(self.capacity)
            if not acknowledgements or any(value!=ord('1') for value in acknowledgements):raise ConnectionError('Frame consumer stopped')
            self.credits=len(acknowledgements)
        metadata=json.dumps({'session_id':session_id,'task_id':task_id,'frame_index':frame_index,'width':self.width,'height':self.height},separators=(',',':')).encode()
        self.connection.sendall(struct.pack('!I',len(metadata))+metadata)
        self.connection.sendall(memoryview(np.ascontiguousarray(image)).cast('B'));self.credits-=1

    def close(self):
        try:self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        self.connection.close()
