"""Dependency-free protobuf subset used by the Kuaishou live socket."""
from __future__ import annotations
import gzip

UNKNOWN=0; CS_HEARTBEAT=1; SC_HEARTBEAT_ACK=101; CS_ENTER_ROOM=200; SC_ENTER_ROOM_ACK=300; SC_FEED_PUSH=310; SC_LIVE_WATCHING_LIST=340

def _vi(v):
    out=bytearray()
    while v>127: out.append((v&127)|128);v>>=7
    out.append(v);return bytes(out)
def _rv(data,pos):
    value=shift=0
    while pos<len(data):
        b=data[pos];pos+=1;value|=(b&127)<<shift
        if not b&128:return value,pos
        shift+=7
    raise ValueError("truncated varint")
def _fields(data):
    pos=0
    while pos<len(data):
        tag,pos=_rv(data,pos);num,wire=tag>>3,tag&7
        if wire==0:value,pos=_rv(data,pos)
        elif wire==2:
            n,pos=_rv(data,pos);value=data[pos:pos+n];pos+=n
            if len(value)!=n:raise ValueError("truncated field")
        elif wire==1:value,pos=data[pos:pos+8],pos+8
        elif wire==5:value,pos=data[pos:pos+4],pos+4
        else:raise ValueError(f"wire {wire} unsupported")
        yield num,wire,value
def _f(num,value,wire=2):
    if wire==0:return _vi(num<<3)+_vi(int(value))
    raw=value.encode() if isinstance(value,str) else bytes(value);return _vi((num<<3)|2)+_vi(len(raw))+raw

class _Repeated(list):
    pass
class _Msg:
    @classmethod
    def FromString(cls,data):obj=cls();obj._parse(data);return obj
    def SerializeToString(self):return self._serialize()

class SocketMessage(_Msg):
    UNKNOWN=0;NONE=1;GZIP=2;AES=3
    def __init__(self,payloadType=0,compressionType=0,payload=b""):self.payloadType=payloadType;self.compressionType=compressionType;self.payload=payload
    def _parse(self,data):
        for n,w,v in _fields(data):
            if n==1:self.payloadType=v
            elif n==2:self.compressionType=v
            elif n==3:self.payload=v
    def _serialize(self):return _f(1,self.payloadType,0)+_f(2,self.compressionType,0)+_f(3,self.payload)
class CSWebEnterRoom(_Msg):
    def __init__(self,liveStreamId="",token="",pageId="",**kw):self.liveStreamId=liveStreamId;self.token=token;self.pageId=pageId
    def _parse(self,data):
        for n,w,v in _fields(data):
            if n==1:self.token=v.decode()
            elif n==2:self.liveStreamId=v.decode()
            elif n==7:self.pageId=v.decode()
    def _serialize(self):return _f(1,self.token)+_f(2,self.liveStreamId)+_f(7,self.pageId)
class CSWebHeartbeat(_Msg):
    def __init__(self,timestamp=0):self.timestamp=timestamp
    def _parse(self,data):
        for n,w,v in _fields(data):
            if n==1:self.timestamp=v
    def _serialize(self):return _f(1,self.timestamp,0)
class SCWebEnterRoomAck(_Msg):
    def __init__(self,heartbeatIntervalMs=0,**kw):self.heartbeatIntervalMs=heartbeatIntervalMs
    def _parse(self,data):
        for n,w,v in _fields(data):
            if n==3:self.heartbeatIntervalMs=v
    def _serialize(self):return _f(3,self.heartbeatIntervalMs,0)
class SimpleUserInfo(_Msg):
    def __init__(self,principalId="",userName="",headUrl="",**kw):self.principalId=principalId;self.userName=userName;self.headUrl=headUrl
    def _parse(self,data):
        for n,w,v in _fields(data):
            if n==1:self.principalId=v.decode()
            elif n==2:self.userName=v.decode()
            elif n==3:self.headUrl=v.decode()
    def _serialize(self):return _f(1,self.principalId)+_f(2,self.userName)+_f(3,self.headUrl)
class WebCommentFeed(_Msg):
    def __init__(self,user=None,content="",**kw):self.user=user or SimpleUserInfo();self.content=content
    def _parse(self,data):
        for n,w,v in _fields(data):
            if n==2:self.user=SimpleUserInfo.FromString(v)
            elif n==3:self.content=v.decode()
    def _serialize(self):return _f(2,self.user.SerializeToString())+_f(3,self.content)
class WebLikeFeed(_Msg):
    def __init__(self,user=None,**kw):self.user=user or SimpleUserInfo()
    def _parse(self,data):
        for n,w,v in _fields(data):
            if n==2:self.user=SimpleUserInfo.FromString(v)
    def _serialize(self):return _f(2,self.user.SerializeToString())
class WebGiftFeed(_Msg):
    def __init__(self,user=None,giftId=0,batchSize=0,comboCount=0,**kw):self.user=user or SimpleUserInfo();self.giftId=giftId;self.batchSize=batchSize;self.comboCount=comboCount
    def _parse(self,data):
        for n,w,v in _fields(data):
            if n==2:self.user=SimpleUserInfo.FromString(v)
            elif n==4:self.giftId=v
            elif n==7:self.batchSize=v
            elif n==8:self.comboCount=v
    def _serialize(self):return _f(2,self.user.SerializeToString())+_f(4,self.giftId,0)+_f(7,self.batchSize,0)+_f(8,self.comboCount,0)
class SCWebFeedPush(_Msg):
    def __init__(self,displayWatchingCount="",displayLikeCount="",commentFeeds=None,likeFeeds=None,giftFeeds=None,**kw):self.displayWatchingCount=displayWatchingCount;self.displayLikeCount=displayLikeCount;self.commentFeeds=_Repeated(commentFeeds or []);self.likeFeeds=_Repeated(likeFeeds or []);self.giftFeeds=_Repeated(giftFeeds or [])
    def _parse(self,data):
        for n,w,v in _fields(data):
            if n==1:self.displayWatchingCount=v.decode()
            elif n==2:self.displayLikeCount=v.decode()
            elif n==5:self.commentFeeds.append(WebCommentFeed.FromString(v))
            elif n==8:self.likeFeeds.append(WebLikeFeed.FromString(v))
            elif n==9:self.giftFeeds.append(WebGiftFeed.FromString(v))
    def _serialize(self):return b"".join([_f(1,self.displayWatchingCount),_f(2,self.displayLikeCount),*(_f(5,x.SerializeToString()) for x in self.commentFeeds),*(_f(8,x.SerializeToString()) for x in self.likeFeeds),*(_f(9,x.SerializeToString()) for x in self.giftFeeds)])
class SCWebLiveWatchingUsers(_Msg):
    def __init__(self,displayWatchingCount="",**kw):self.displayWatchingCount=displayWatchingCount
    def _parse(self,data):
        for n,w,v in _fields(data):
            if n==2:self.displayWatchingCount=v.decode()
    def _serialize(self):return _f(2,self.displayWatchingCount)
