"""Recovered Kuaishou live message handling."""

import asyncio
import json
import base64
import os
import ssl
from contextlib import suppress
from random import choice, uniform
from time import time

from .protocol import (
    decode_frame, encode_enter_room, encode_heartbeat, iter_comments, iter_gifts, iter_likes, proto,
)


# KsLive.pyd initializes HEARTBEAT_INTERVAL to 20 at 0x18002c0b0.
HEARTBEAT_INTERVAL = 20
MIN_RECONNECT_DELAY = 1
MAX_RECONNECT_DELAY = 5
MAX_RECONNECT_ATTEMPTS = 10
_PAGE_ID_ALPHABET = "bjectSymhasOwnProp-0123456789ABCDEFGHIJKLMNQRTUVWXYZ_dfgiklquvxz"
gift_info_global = {}


class KuaishouLiveClient:
    def __init__(self, live_stream_id, token, ws_url, room_id=None):
        self.live_stream_id = live_stream_id
        self.token = token
        self.ws_url = ws_url
        self.page_id = self._generate_page_id()
        self.sec_websocket_key = self._generate_websocket_key()
        self.reconnect_attempts = 0
        self.ssl_context = self._create_ssl_context()
        self.encoded_data = self._prepare_enter_room_message()
        self.room_id = room_id
        self.heartbeat_interval_ms = HEARTBEAT_INTERVAL * 1000

    def _generate_page_id(self):
        prefix = "".join(choice(_PAGE_ID_ALPHABET) for _ in range(16))
        return prefix + str(int(time() * 1000))

    async def start(self):
        await self._connect()

    def _calculate_reconnect_delay(self):
        attempt = self.reconnect_attempts
        delay = MIN_RECONNECT_DELAY * 1.5**attempt
        return min(delay * uniform(0.8, 1.2), MAX_RECONNECT_DELAY)

    async def _connect(self):
        from websockets import connect

        async with connect(
            self.ws_url,
            extra_headers=self._get_headers(),
            ssl=self.ssl_context,
            ping_interval=None,
            close_timeout=10,
        ) as socket:
            self.reconnect_attempts = 0
            await self._on_open(socket)

    async def _send_heartbeat(self, ws):
        from websockets.exceptions import ConnectionClosed

        try:
            while True:
                timestamp = int(time() * 1000)
                await ws.send(encode_heartbeat(timestamp))
                print(f"[心跳][{self.room_id}] 心跳包已发送，时间: {timestamp}")
                await asyncio.sleep(HEARTBEAT_INTERVAL)
        except ConnectionClosed as error:
            print(f"[心跳][{self.room_id}] 连接问题: {error}")
        except Exception as error:
            print(f"[心跳][{self.room_id}] 意外错误: {error}")


    async def _handle_message(self, socket_message):
        kind, payload = decode_frame(socket_message)
        if kind == proto.SC_FEED_PUSH:
            await self._handle_feed_push(payload)
        elif kind == proto.SC_ENTER_ROOM_ACK:
            await self._handle_enter_room_ack(payload)
        elif kind == getattr(proto,"SC_LIVE_WATCHING_LIST",None):
            await self._handle_watching_list(payload)

    async def _handle_feed_push(self, feed_push):
        await self._handle_comments(feed_push.commentFeeds)
        await self._handle_gifts(feed_push.giftFeeds)
        await self._handle_likes(feed_push.likeFeeds)
        await self._handle_stats(feed_push)

    async def _handle_stats(self,feed_push):
        stats_data={"type":"stats","status":feed_push.displayWatchingCount,"like_count":feed_push.displayLikeCount}
        await self._forward_message(json.dumps(stats_data,ensure_ascii=False))

    async def _handle_watching_list(self,payload):
        stats_data={"type":"stats","status":payload.displayWatchingCount}
        await self._forward_message(json.dumps(stats_data,ensure_ascii=False))

    def _create_ssl_context(self):
        context=ssl.create_default_context(); context.check_hostname=True; context.verify_mode=ssl.CERT_REQUIRED
        return context
    def _generate_websocket_key(self): return base64.b64encode(os.urandom(16)).decode("ascii")
    def _get_headers(self):
        return {"Origin":"https://live.kuaishou.com","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
                "Sec-WebSocket-Version":"13","Sec-WebSocket-Key":self.sec_websocket_key,"Sec-WebSocket-Extensions":"permessage-deflate; client_max_window_bits"}
    def _prepare_enter_room_message(self):
        return encode_enter_room(self.live_stream_id,self.token,self.page_id).hex()

    async def _handle_enter_room_ack(self,payload):
        if payload.heartbeatIntervalMs>0: self.heartbeat_interval_ms=payload.heartbeatIntervalMs
    async def _handle_comments(self,comments):
        feed=proto.SCWebFeedPush(); feed.commentFeeds.extend(comments)
        for event in iter_comments(feed): await self._forward_message(json.dumps(event,ensure_ascii=False))
    async def _handle_likes(self,likes):
        feed=proto.SCWebFeedPush(); feed.likeFeeds.extend(likes)
        for event in iter_likes(feed): await self._forward_message(json.dumps(event,ensure_ascii=False))
    async def _handle_gifts(self,gifts):
        feed=proto.SCWebFeedPush(); feed.giftFeeds.extend(gifts)
        for event in iter_gifts(feed):
            info=self.get_gift_info(event["gift_id"])
            if info:
                event["gift_name"]=info.get("name") if isinstance(info,dict) else str(info)
                if isinstance(info,dict):
                    if info.get("pic_url"): event["gift_pic_url"]=info["pic_url"]
                    if info.get("price") is not None: event["price"]=info["price"]
            await self._forward_message(json.dumps(event,ensure_ascii=False))
    def get_gift_info(self,gift_id):
        if gift_id in gift_info_global:
            return gift_info_global[gift_id]
        return {"name": f"未知礼物({gift_id})", "price": 0, "type": 0, "pic_url": ""}

    async def _send_initial_data(self, ws):
        await ws.send(bytes.fromhex(self.encoded_data))
        print(f"[数据][{self.room_id}] 初始数据已发送")

    async def _on_open(self, ws):
        print(f"[已连接][{self.room_id}] WebSocket连接已建立")
        await self._send_initial_data(ws)
        heartbeat_task = asyncio.create_task(self._send_heartbeat(ws))
        message_task = asyncio.create_task(self._on_message(ws))
        try:
            await asyncio.gather(heartbeat_task, message_task)
        except Exception as error:
            print(f"[任务错误][{self.room_id}] 意外错误: {error}")
    async def _on_message(self, ws):
        async for socket_message in ws:
            try:
                await self._handle_message(socket_message)
            except Exception as error:
                print(f"[解析错误] {error}")
    async def _on_error(self, ws, error):
        print(f"[错误] {error}")
        await self._on_close(ws)

    async def _on_close(self, ws):
        print("[已关闭] WebSocket连接已关闭")
        await self._reconnect()
    async def _reconnect(self):
        if self.reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
            print(f"[重连] 达到最大重连尝试次数 ({MAX_RECONNECT_ATTEMPTS})，放弃连接")
            return None
        delay = self._calculate_reconnect_delay()
        self.reconnect_attempts += 1
        print(f"[重连] 第{self.reconnect_attempts}次尝试，等待 {delay:.2f} 秒...")
        await asyncio.sleep(delay)
        await self._connect()

    async def _forward_message(self, json_data):
        return None


def parse_live_info(data):
    """Extract connection parameters from a decoded room data object."""
    live_stream_id = data.get("liveStreamId")
    token = data.get("token")
    urls = data.get("websocketUrls")
    if not isinstance(live_stream_id, str) or not live_stream_id:
        return None
    if not isinstance(token, str) or not token or not isinstance(urls, (tuple, list)):
        return None
    for url in urls:
        if isinstance(url, str) and url.startswith(("wss://", "ws://")):
            return {"live_stream_id": live_stream_id, "token": token, "ws_url": url}
    return None


async def get_live_info_from_url(live_url):
    from .hq import Tool
    try:
        tool = Tool(live_url)
        live_id = tool.getLiveRoomId()
        room_info = tool.processLiveId(live_id)
        if room_info and "data" in room_info and room_info["data"].get("result") == 1:
            ws_info = room_info["data"]
            live_stream_id = ws_info.get("liveStreamId") or live_id
            token = ws_info.get("token")
            ws_url = None
            if ws_info.get("websocketUrls"):
                ws_url = ws_info["websocketUrls"][0]
            elif "webSocketUrl" in ws_info:
                ws_url = ws_info.get("webSocketUrl")
            if live_stream_id and token and ws_url:
                return {"live_stream_id": live_stream_id, "token": token, "ws_url": ws_url}
        return None
    except Exception as error:
        print(f"获取直播间信息出错: {error}")
        return None


async def fetch_gift_info_global():
    import aiohttp
    url = "https://livev.m.chenzhongtech.com/rest/wd/live/gift/all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"[礼物] 全局获取失败: HTTP {response.status}")
                    return None
                result = await response.json()
                if "data" not in result or not isinstance(result["data"], (list, tuple)):
                    print(f"[礼物] 全局获取失败: {result}")
                    return None
                for gift_info in result["data"]:
                    gift_pic = ""
                    if gift_info.get("picUrl"):
                        first_picture = gift_info["picUrl"][0]
                        if "url" in first_picture:
                            gift_pic = first_picture["url"]
                    gift_info_global[gift_info["id"]] = {
                        "name": gift_info["name"],
                        "price": gift_info["unitPrice"],
                        "type": gift_info["type"],
                        "pic_url": gift_pic,
                    }
                print(f"[礼物] 全局获取到 {len(gift_info_global)} 个礼物信息")
    except Exception as error:
        print(f"[礼物] 全局获取出错: {error}")
    return None


async def main(live_url):
    info = await get_live_info_from_url(live_url)
    if not info:
        raise ValueError("无法从快手直播地址获取连接信息")

    class ConsoleClient(KuaishouLiveClient):
        async def _forward_message(self, json_data):
            print(json_data)

    client = ConsoleClient(**info)
    try:
        await fetch_gift_info_global()
    except Exception:
        pass
    await client.start()
    return client
