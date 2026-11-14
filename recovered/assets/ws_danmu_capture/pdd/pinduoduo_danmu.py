#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import json
import os
try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None
import struct
import zlib
try:
    from google.protobuf.json_format import MessageToDict
except ImportError:
    def MessageToDict(message, preserving_proto_field_name=True):
        return {name: getattr(message, name) for name in getattr(message, "FIELD_NAMES", ())}
try:
    from . import pinduoduo_pb2
except ImportError:
    import assets.ws_danmu_capture.pdd.pinduoduo_pb2 as pinduoduo_pb2
import time
import websockets
import inspect
from pathlib import Path
from urllib.parse import urlparse


def normalize_pdd_live_url(value):
    parsed = urlparse(str(value or "").strip())
    hostname = (parsed.hostname or "").lower().rstrip(".")
    approved = ("pinduoduo.com", "yangkeduo.com")
    if (parsed.scheme != "https" or parsed.username or parsed.password or
            not any(hostname == domain or hostname.endswith("." + domain) for domain in approved)):
        raise ValueError("仅支持拼多多官方 HTTPS 直播链接")
    return parsed.geturl()


MAX_FRAME_BYTES = 8 * 1024 * 1024


def _gzip_decompress_limited(data, limit=MAX_FRAME_BYTES):
    decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)
    output = decompressor.decompress(data, limit + 1)
    if len(output) > limit or decompressor.unconsumed_tail:
        raise ValueError("拼多多弹幕压缩帧超过大小限制")
    output += decompressor.flush()
    if len(output) > limit:
        raise ValueError("拼多多弹幕解压结果超过大小限制")
    return output


class PinduoduoDanmu:
    def __init__(self):
        # 确保cookies文件路径是相对于当前脚本目录的
        default_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".shuziren") / "Shuziren"
        self.cookies_path = os.fspath((default_root / "pdd_cookies.json").resolve())
        self.browser = None
        self._is_running = False
        self.clients = set()
        self.playwright_task = None

    async def broadcast(self, message):
        """向所有连接的客户端广播消息"""
        if self.clients:
            # 使用websockets.broadcast来简化向多个客户端发送消息的过程
            result = websockets.broadcast(self.clients, json.dumps(message, ensure_ascii=False))
            if inspect.isawaitable(result):
                await result

    async def on_frame_received(self, payload):
        """处理接收到的WebSocket帧"""
        try:
            if len(payload) > MAX_FRAME_BYTES:
                raise ValueError("拼多多弹幕帧超过大小限制")
            # 将WebSocket二进制数据转换为十六进制字符串
            hex_string = payload.hex()
            
            # 解析头部获取body长度
            bytes_data = payload
            if len(bytes_data) >= 16:
                body_len = struct.unpack('>I', bytes_data[12:16])[0]
                body_end = 16 + body_len
                if body_len > MAX_FRAME_BYTES or body_end > len(bytes_data):
                    raise ValueError("拼多多弹幕帧长度无效")
                data = bytes_data[16:body_end]
            else:
                data = bytes_data  # 数据过短时直接使用全部数据

            # 检查并解压gzip数据
            for i in range(len(data) - 1):
                if data[i] == 0x1f and data[i + 1] == 0x8b:
                    try:
                        # 解压gzip数据
                        decompressed = _gzip_decompress_limited(data[i:])
                        
                        # 尝试解析为Protobuf消息
                        try:
                            message = pinduoduo_pb2.Command()
                            message.ParseFromString(decompressed)
                            
                            # 检查Protobuf消息中是否包含body字段, body里才是真正的弹幕信息
                            if message.body:
                                # body字段是bytes类型，需要解码为字符串
                                body_text = message.body.decode('utf-8')
                                # 将解码后的JSON文本交给parse_message处理
                                await self.parse_message(body_text)
                            else:
                                # 打印不含body的消息，方便调试（例如心跳或ACK）
                                result = MessageToDict(message, preserving_proto_field_name=True)
                                print(f"收到不含弹幕内容的Protobuf消息: {json.dumps(result, ensure_ascii=False)}")
                            
                            # 成功处理，返回，避免后续的错误解码
                            return
                        except Exception as e:
                            # 如果protobuf解析失败，可能是纯文本压缩，尝试直接解码
                            pass
                            
                        # 尝试多种编码解码并打印
                        for encoding in ['utf-8', 'gbk', 'gb18030', 'latin-1']:
                            try:
                                decoded = decompressed.decode(encoding)
                                # 尝试解析JSON
                                try:
                                    await self.parse_message(decoded)
                                    return
                                except:
                                    print(f"解压并解码成功 ({encoding}): {decoded}")
                                return
                            except UnicodeDecodeError:
                                continue
                    except Exception as e:
                        print(f"解压失败: {e}")
                    break

            # 直接尝试解码原始数据
            for encoding in ['utf-8', 'gbk', 'gb18030', 'latin-1']:
                try:
                    decoded = data.decode(encoding)
                    print(f"原始数据解码 ({encoding}): {decoded}")
                    return
                except UnicodeDecodeError:
                    continue

            print(f"收到未能解析的WebSocket消息: {hex_string[:100]}...")
                
        except Exception as e:
            print(f"处理WebSocket消息时出错: {e}")

    async def parse_message(self, message_text):
        """解析并格式化显示消息"""
        try:
            decoder = json.JSONDecoder()
            pos = 0
            while pos < len(message_text):
                # 跳过消息开头可能存在的非JSON字符
                if message_text[pos] not in ['[', '{']:
                    pos += 1
                    continue
                
                try:
                    messages, end_pos = decoder.raw_decode(message_text, pos)
                    pos = end_pos
                    
                    if not isinstance(messages, list):
                        continue
                    
                    # 打印所有收到的消息类型
                    msg_types = [msg.get("message_type", "unknown") for msg in messages]
                    if msg_types: 
                        print(f"接收到消息类型: {', '.join(msg_types)}")
                        
                    for msg in messages:
                        msg_type = msg.get("message_type", "unknown")
                        
                        # 观众数量消息
                        if msg_type == "live_audience_num":
                            audience = msg.get("message_data", {}).get("live_audience_num", 0)
                            audience_desc = msg.get("message_data", {}).get("live_audience_num_desc", "")
                            await self.broadcast({'type': 'online', 'nickname': '', 'content': f"{audience} ({audience_desc})"})
                            print(f"👥 观众数: {audience} ({audience_desc})")
                        
                        # 新增：点赞数消息
                        elif msg_type == "show_thumb_up_count":
                            thumb_data = msg.get("message_data", {})
                            total_count = thumb_data.get("total_count", 0)
                            total_count_tip = thumb_data.get("total_count_tip", "")
                            await self.broadcast({'type': 'like_count', 'nickname': '', 'content': f"{total_count} ({total_count_tip})"})
                            print(f"👍 点赞数: {total_count} ({total_count_tip})")
                        
                        # 直用户弹幕消息 
                        elif msg_type == "live_chat":
                            chat_data = msg.get("message_data", {})
                            chat_list = chat_data.get("live_chat_list", [])
                            for chat in chat_list:
                                info = {
                                    "type": "弹幕",
                                    "nickname": chat.get("nickname", ""),
                                    "content": chat.get("chat_message", "")
                                }
                                await self.broadcast(info)
                                print(json.dumps({
                                    "时间": time.strftime("%H:%M:%S"),
                                    "类型": "聊天",
                                    "用户ID": chat.get("uid", ""),
                                    "用户名字": chat.get("nickname", ""),
                                    "内容": chat.get("chat_message", "")
                                }, ensure_ascii=False))
                        
                        # 用户进入直播间
                        elif msg_type == "live_chat_notice":
                            notice_list = msg.get("message_data", {}).get("live_chat_notice_list", [])
                            for notice in notice_list:
                                notice_type = notice.get("live_chat_notice_type", "")
                                notice_data = notice.get("live_chat_notice_data", {})
                                user_list = notice_data.get("user_list", [])
                                
                                if notice_type == "enter":
                                    for user in user_list:
                                        info = {
                                            "type": "进入直播间",
                                            "nickname": user.get("nickname", ""),
                                            "content": "进入直播间"
                                        }
                                        await self.broadcast(info)
                                        print(json.dumps({
                                            "时间": time.strftime("%H:%M:%S"),
                                            "类型": "进入",
                                            "用户ID": user.get("uid", ""),
                                            "用户名字": user.get("nickname", ""),
                                            "内容": "进入直播间"
                                        }, ensure_ascii=False))
                                
                                elif notice_type == "favorite":
                                    for user in user_list:
                                        info = {
                                            "type": "关注",
                                            "nickname": user.get("nickname", ""),
                                            "content": "关注了主播"
                                        }
                                        await self.broadcast(info)
                                        print(json.dumps({
                                            "时间": time.strftime("%H:%M:%S"),
                                            "类型": "关注",
                                            "用户ID": user.get("uid", ""),
                                            "用户名字": user.get("nickname", ""),
                                            "内容": "关注了主播"
                                        }, ensure_ascii=False))
                                
                                elif notice_type == "group_open":
                                    goods_info = notice_data.get("goods_info", {})
                                    goods_name = goods_info.get("goods_name", "")
                                    if user_list:
                                        nickname = user_list[0].get("nickname", "")
                                        info = {'type': '拼单', 'nickname': nickname, 'content': f"发起拼单: {goods_name}"}
                                        await self.broadcast(info)
                                        print(f"🛒 {nickname} 发起拼单: {goods_name}")
                                    else:
                                        info = {'type': '拼单', 'nickname': '', 'content': f"有人发起拼单: {goods_name}"}
                                        await self.broadcast(info)
                                        print(f"🛒 有人发起拼单: {goods_name}")
                                
                                # 新增 group_buy 类型处理
                                elif notice_type == "group_buy":
                                    goods_info = notice_data.get("goods_info", {})
                                    goods_name = goods_info.get("goods_name", "")
                                    user_list = notice_data.get("user_list", [])
                                    user_names = [user.get("nickname", "") for user in user_list if user.get("nickname", "")]
                                    if user_names and goods_name:
                                        info = {'type': '拼单成功', 'nickname': '、'.join(user_names), 'content': f"拼单成功: {goods_name}"}
                                        await self.broadcast(info)
                                        print(f"🤝 {'、'.join(user_names)} 拼单成功: {goods_name}")
                                    elif goods_name:
                                        info = {'type': '拼单成功', 'nickname': '', 'content': f"有人拼单成功: {goods_name}"}
                                        await self.broadcast(info)
                                        print(f"🤝 有人拼单成功: {goods_name}")
                                
                                elif notice_type == "hot_sell":
                                    goods_info = notice_data.get("goods_info", {})
                                    goods_name = goods_info.get("goods_name", "")
                                    price = goods_info.get("price", 0) / 100
                                    info = {'type': '商品', 'nickname': '', 'content': f"热卖商品: {goods_name} ¥{price}"}
                                    await self.broadcast(info)
                                    print(f"🔥 热卖商品: {goods_name} ¥{price}")
                                
                                elif notice_type == "buying":
                                    content = notice_data.get("content", "")
                                    info = {'type': '购买', 'nickname': '', 'content': content}
                                    await self.broadcast(info)
                                    print(f"🛍️ {content}")
                                
                        elif msg_type == "live_chat_ext_v2":
                            ext_list = msg.get("message_data", {}).get("live_chat_ext_list", [])
                            for ext in ext_list:
                                if ext.get("sub_type") == 121:
                                    body = ext.get("body", {})
                                    info = {
                                        "type": "点赞",
                                        "nickname": next((element.get("data", "") for element in body.get("elements", []) if element.get("type") == "nickname"), ""),
                                        "content": next((element.get("data", "") for element in body.get("elements", []) if element.get("type") == "content"), "")
                                    }
                                    await self.broadcast(info)
                                    print(json.dumps({
                                        "时间": time.strftime("%H:%M:%S"),
                                        "类型": "点赞",
                                        "用户ID": ext.get("uin", ""),
                                        "用户名字": info["nickname"],
                                        "内容": info["content"]
                                    }, ensure_ascii=False))


                                elif ext.get("sub_type") == 120:
                                    body = ext.get("body", {})
                                    nickname = ""
                                    content = ""
                                    for element in body.get("elements", []):
                                        if element.get("type") == "nickname":
                                            nickname = element.get("data", "")
                                        elif element.get("type") == "content":
                                            content = element.get("data", "")
                                    if nickname and content:
                                        info = {'type': '弹幕', 'nickname': nickname, 'content': content}
                                        await self.broadcast(info)
                                        print(f"🛒 {nickname}{content}")
                except json.JSONDecodeError:
                    pos += 1

        except Exception as e:
            print(f"parse_message 解析异常: {e}")

    async def stop(self):
        """停止浏览器和任务"""
        self._is_running = False
        if self.playwright_task and not self.playwright_task.done():
            self.playwright_task.cancel()
        if self.browser:
            await self.browser.close()
            self.browser = None
            print("浏览器已关闭")

    def find_chrome_path(self):
        """查找Chrome浏览器路径"""
        possible_paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        ]
        if 'CHROME_PATH' in os.environ and os.path.exists(os.environ['CHROME_PATH']):
            return os.environ['CHROME_PATH']
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

    async def save_cookies(self, context):
        """保存浏览器cookies到文件"""
        try:
            cookies = await context.cookies()
            Path(self.cookies_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.cookies_path, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            print(f"Cookies已保存到: {self.cookies_path}")
        except Exception as e:
            print(f"保存Cookies失败: {e}")
    
    async def load_cookies(self, context):
        """从文件加载cookies到浏览器"""
        try:
            if os.path.exists(self.cookies_path):
                with open(self.cookies_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                await context.add_cookies(cookies)
                print(f"成功加载Cookies，共{len(cookies)}个")
                return True
            else:
                print("Cookies文件不存在，将创建新会话")
                return False
        except Exception as e:
            print(f"加载Cookies失败: {e}")
            return False
            

    async def run_playwright(self, live_url, headless=True):
        if async_playwright is None:
            raise RuntimeError("缺少 playwright；请安装 playwright 并执行 playwright install chromium")
        """主函数，启动浏览器并连接WebSocket"""
        self._is_running = True
        # 自动查找Chrome浏览器路径
        chrome_path = self.find_chrome_path()
        
        # 设置浏览器参数
        args = []
        if headless:
            args.append('--headless=new')
        
        print(f"正在启动浏览器...")
        async with async_playwright() as p:
            self.browser = await p.chromium.launch(
                headless=headless,
                channel='chrome',
                executable_path=chrome_path,
                args=args
            )
            
            # 使用移动端UA以获取更好的兼容性
            mobile_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            context = await self.browser.new_context(user_agent=mobile_ua, viewport={'width': 500, 'height': 800})
            
            # 尝试加载已保存的cookies
            has_cookies = await self.load_cookies(context)
            
            page = await context.new_page()

            # 注册websocket消息处理
            def handle_websocket(ws):
                print(f"WebSocket连接已建立: {ws.url}")
                ws.on("framereceived", lambda payload: asyncio.create_task(self.on_frame_received(payload)))
                
            page.on("websocket", handle_websocket)

            print(f"正在打开直播页面: {live_url}")
            await page.goto(live_url)
            await page.wait_for_load_state("domcontentloaded")
            
        
            
            # 等待1分钟后保存cookies以便下次使用
            print("将在1分钟后保存cookies...")
            await asyncio.sleep(60)
            await self.save_cookies(context)
            
            print("已连接，等待弹幕消息...")
            
            # 持续运行，接收WebSocket消息
            try:
                while self._is_running:
                    await asyncio.sleep(1)
            except (asyncio.CancelledError, KeyboardInterrupt):
                print("Playwright 任务被取消或手动停止")
            finally:
                await self.stop()
    
    def log_interesting_requests(self, request):
        """只关注WebSocket连接"""
        # 不记录API请求，仅保留方法以兼容现有代码
        pass
        

    async def handler(self, websocket, path=None):
        """处理WebSocket连接"""
        self.clients.add(websocket)
        print(f"新客户端连接: {websocket.remote_address}, 当前客户端数: {len(self.clients)}")
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if 'url' in data:
                        live_url = normalize_pdd_live_url(data['url'])
                        if self.playwright_task is None or self.playwright_task.done():
                            print(f"收到URL，启动Playwright: {live_url}")
                            # 设置为非无头模式启动，方便扫码登录
                            self.playwright_task = asyncio.create_task(self.run_playwright(live_url, headless=False))
                        else:
                            print("Playwright已在运行中，忽略新的URL")
                except json.JSONDecodeError:
                    print(f"收到非JSON消息: {message}")
                except Exception as e:
                    print(f"处理消息时出错: {e}")
            await websocket.wait_closed()
        finally:
            self.clients.remove(websocket)
            print(f"客户端断开连接: {websocket.remote_address}, 当前客户端数: {len(self.clients)}")
            # 可选：当最后一个客户端断开时停止Playwright
            if not self.clients and self.playwright_task:
                print("最后一个客户端已断开，正在停止Playwright...")
                await self.stop()


    async def main_server(self, host="127.0.0.1", port=8888):
        """启动WebSocket服务器"""
        print("启动 PDD 弹幕服务器...")
        async with websockets.serve(self.handler, host, port):
            print(f"WebSocket 服务器已启动，监听地址: ws://{host}:{port}")
            await asyncio.Future()  # 永久运行，直到被中断


if __name__ == "__main__":
    danmu_client = PinduoduoDanmu()
    try:
        asyncio.run(danmu_client.main_server())
    except KeyboardInterrupt:
        print("服务器被手动停止") 
