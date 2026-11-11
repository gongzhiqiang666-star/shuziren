"""Own loopback console: python -m scripts.local_console --data-directory PATH."""
import argparse
import base64
import binascii
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import socket
import sqlite3
import threading
from urllib.parse import urlsplit, parse_qs

from scripts.local_console_config import ConfigError, ConfigStore, preflight
from scripts.product_store import ProductStore, Conflict, ProductError
from scripts.voice_store import VoiceStore, VoiceError
from scripts.avatar_store import AvatarStore, AvatarError
from scripts.console_live import ConsoleLive
from scripts.console_taobao import ConsoleTaobao
from scripts.console_comment_reply import ConsoleCommentReply

WEB = Path(__file__).parent / "local-console"


class ConsoleServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def server_close(self):
        cleanup = getattr(self, 'cleanup_tasks', None)
        if cleanup: cleanup()
        super().server_close()


class InstanceLock:
    """OS-held lock; a crashed process releases it without trusting a stale PID."""
    def __init__(self, directory):
        self.path = Path(directory) / "console.lock"
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise OSError("同一配置目录的控制台已运行") from None
        return self

    def __exit__(self, *args):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def create_server(store, port=None, *, tts_engine="indextts", tts_model_root=None):
    token = secrets.token_urlsafe(32)
    lock = threading.RLock()
    def products():
        return ProductStore(store.directory)
    task_manager = None
    tts_manager = None
    avatar_manager = None
    render_manager = None
    live_manager = None
    taobao = ConsoleTaobao(store.directory)
    replies = ConsoleCommentReply()
    tasks_closed = False
    def live_label():
        status = live_manager.state()['status'] if live_manager else 'idle'
        return {'idle': '未启动', 'preparing': '准备中', 'running': '本机输出中',
                'stopping': '停止中', 'stopped': '已停止', 'failed': '输出失败'}[status]
    def tasks():
        nonlocal task_manager
        with lock:
            if tasks_closed: raise ProductError('控制台正在退出')
            if task_manager is None:
                from scripts.llm_tasks import LLMTasks
                task_manager = LLMTasks(products())
            return task_manager
    def cleanup():
        nonlocal tasks_closed
        with lock:
            tasks_closed = True
            replies.close()
            taobao.close()
            if live_manager is not None: live_manager.close()
            if task_manager is not None: task_manager.close()
            if render_manager is not None: render_manager.close()
            if tts_manager is not None: tts_manager.close()
            if avatar_manager is not None: avatar_manager.close()
    def preparation():
        nonlocal avatar_manager
        with lock:
            if tasks_closed: raise AvatarError('控制台正在退出')
            root=preflight(store.load())['runtime_root']
            if not root: raise AvatarError('请先配置形象制作运行资源目录')
            if avatar_manager is None:
                from scripts.avatar_tasks import AvatarTasks
                avatar_manager=AvatarTasks(root,store.directory)
            elif Path(root).resolve()!=avatar_manager.runtime:
                raise Conflict('运行资源目录已修改，请重启控制台后制作')
            return avatar_manager
    def tts():
        nonlocal tts_manager
        with lock:
            if tasks_closed: raise ProductError('控制台正在退出')
            root=preflight(store.load())['runtime_root']
            if not root: raise ProductError('请先配置TTS运行资源目录')
            if tts_manager is None:
                from scripts.tts_tasks import TTSTasks
                tts_manager=TTSTasks(root,store.directory,engine=tts_engine,model_root=tts_model_root)
            elif Path(root).resolve()!=tts_manager.runtime:
                raise Conflict('运行资源目录已修改，请重启控制台后合成')
            return tts_manager
    def renders():
        nonlocal render_manager
        with lock:
            if tasks_closed: raise ProductError('控制台正在退出')
            root=preflight(store.load())['runtime_root']
            if not root: raise ProductError('请先配置视频合成运行资源目录')
            if render_manager is None:
                from scripts.render_tasks import RenderTasks
                render_manager=RenderTasks(root,store.directory,tts())
            elif Path(root).resolve()!=render_manager.runtime:
                raise Conflict('运行资源目录已修改，请重启控制台后合成视频')
            return render_manager
    try:
        settings = store.load()
        configured_port = settings["port"]
    except ConfigError:
        configured_port = 5158  # Serve the visible error; never overwrite corrupt settings.

    class Handler(BaseHTTPRequestHandler):
        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True
                logging.info('HTTP客户端已断开，请求已结束')

        def log_message(self, fmt, *args):
            logging.info("HTTP %s", fmt % args)

        def respond(self, status, body, content_type="application/json; charset=utf-8"):
            content = json.dumps(body, ensure_ascii=False).encode("utf-8") if isinstance(body, dict) else body
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # Navigation/exit can cancel a preview while its hashes are checked.
                # Do not reinterpret a disconnected client as a media error or reply twice.
                logging.info('HTTP客户端已断开，响应已停止')

        def trusted_host(self):
            return self.headers.get("Host") == "127.0.0.1:%d" % self.server.server_port

        def do_GET(self):
            if not self.trusted_host():
                return self.respond(403, {"error": "请求地址不允许"})
            path = urlsplit(self.path).path
            try:
                if path == "/api/state":
                    with lock:
                        config = store.load()
                    return self.respond(200, {"config": config, "token": token,
                                              "listening_port": self.server.server_port,
                                              "live_status": live_label(), "data_directory": str(store.directory.resolve())})
                if path == '/api/live/state':
                    return self.respond(200, {'session': live_manager.state() if live_manager else {'status': 'idle'}})
                if path == '/api/taobao/state':
                    return self.respond(200, {'capture': taobao.state(), 'reply': replies.state()})
                if path == '/api/live/devices':
                    try:
                        import sounddevice
                        hosts = sounddevice.query_hostapis()
                        devices = [{'id': index, 'name': device['name'], 'host': hosts[device['hostapi']]['name']}
                                   for index, device in enumerate(sounddevice.query_devices()) if device['max_output_channels']]
                    except (ImportError, OSError, RuntimeError) as error:
                        return self.respond(503, {'error': '无法读取音频设备：' + str(error)})
                    return self.respond(200, {'devices': devices})
                if path == "/api/session":
                    return self.respond(200, {"token": token, "tts_engine": tts_engine})
                if path == '/api/voices':
                    voices=VoiceStore(store.directory)
                    return self.respond(200,{'voices':voices.list(),'selected':voices.selected()})
                if path == '/api/avatars':
                    avatars=AvatarStore(store.directory)
                    return self.respond(200,{'avatars':avatars.list(),'selected':avatars.selected()})
                if path == '/api/avatar-preparation/state':
                    task=(avatar_manager.state() if avatar_manager is not None else
                          preparation().state() if preflight(store.load())['runtime_root'] else None)
                    return self.respond(200,{'task':task})
                if path == '/api/avatars/sample':
                    ids=parse_qs(urlsplit(self.path).query).get('id',[])
                    if len(ids)!=1: raise AvatarError('请选择形象')
                    return self.respond(200,AvatarStore(store.directory).sample(ids[0]),'image/jpeg')
                if path == '/api/tts/state':
                    return self.respond(200,{'task':tts().state()})
                if path == '/api/render/state':
                    task=(render_manager.state() if render_manager is not None else
                          renders().state() if preflight(store.load())['runtime_root'] else None)
                    return self.respond(200,{'task':task})
                if path == '/api/render/video':
                    ids=parse_qs(urlsplit(self.path).query).get('task_id',[])
                    if len(ids)!=1: raise ProductError('请选择有效视频任务')
                    manager=render_manager if render_manager is not None else renders()
                    from scripts.media_http import serve_file
                    return serve_file(self,manager.video_path(ids[0]),'video/mp4')
                if path == '/api/tts/audio':
                    ids=parse_qs(urlsplit(self.path).query).get('task_id',[])
                    if len(ids)!=1: raise ProductError('音频任务参数无效')
                    return self.respond(200,tts().audio(ids[0]),'audio/wav')
                if path == '/api/voices/audio':
                    ids=parse_qs(urlsplit(self.path).query).get('id',[])
                    if len(ids)!=1: raise VoiceError('请选择音色')
                    return self.respond(200,VoiceStore(store.directory).audio_path(ids[0]).read_bytes(),'audio/wav')
                if path == "/api/products":
                    data = products()
                    return self.respond(200, {"products": data.list(), "selected": data.selected()})
                if path == "/api/llm/state":
                    from scripts.console_llm import status
                    return self.respond(200, {**status(), "task":tasks().state()})
                if path == "/api/scripts":
                    query = parse_qs(urlsplit(self.path).query)
                    ids = query.get("product_id", [])
                    if len(ids) != 1:
                        raise ProductError("请选择商品")
                    data=products()
                    return self.respond(200, {"scripts": data.scripts(ids[0]),'selected':data.selected_script(ids[0])})
                filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css",'/voice-recorder.js':'voice-recorder.js'}.get(path)
                if filename:
                    mime = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css",'voice-recorder.js':'text/javascript'}[filename]
                    return self.respond(200, (WEB / filename).read_bytes(), mime + "; charset=utf-8")
                return self.respond(404, {"error": "页面不存在"})
            except Conflict as error:
                self.respond(409,{'error':str(error)})
            except sqlite3.Error:
                self.respond(503, {"error": "商品数据库无法读取，请检查文件与权限；原数据未重置"})
            except (ValueError, OSError) as error:
                self.respond(400, {"error": str(error)})

        def do_POST(self):
            nonlocal live_manager
            origin = "http://127.0.0.1:%d" % self.server.server_port
            if (not self.trusted_host() or self.headers.get("Origin") != origin
                    or not secrets.compare_digest(self.headers.get("X-Console-Token", ""), token)):
                # Drain small rejected requests so Windows does not reset the socket
                # before the client can receive the explicit 403 response.
                length=self.headers.get('Content-Length','0')
                if length.isdecimal() and 0<int(length)<=1048576:
                    self.connection.settimeout(2)
                    try: self.rfile.read(int(length))
                    except OSError: pass
                return self.respond(403, {"error": "请求来源或会话无效，请刷新页面"})
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ConfigError("需要JSON请求")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1048576:
                    raise ConfigError("请求长度无效")
                value = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(value, dict):
                    raise ConfigError("请求必须为对象")
                path = urlsplit(self.path).path
                if path in {'/api/taobao/goods', '/api/taobao/explain'}:
                    fields = {'capture_id'} if path.endswith('/goods') else {'capture_id', 'goods_id'}
                    if set(value) != fields or not isinstance(value['capture_id'], str):
                        raise ProductError('淘宝商品操作参数无效')
                    goods_id = value.get('goods_id')
                    if 'goods_id' in fields and (not isinstance(goods_id, str) or not goods_id.isascii() or not goods_id.isdecimal() or not 5 <= len(goods_id) <= 30):
                        raise ProductError('请选择当前场次的商品')
                    return self.respond(200, taobao.goods(value['capture_id'], goods_id))
                with lock:
                    if path == '/api/taobao/auto-reply':
                        if set(value) != {'enabled'} or type(value['enabled']) is not bool:
                            raise ProductError('自动回复设置无效')
                        if not value['enabled']:
                            return self.respond(200, {'reply': replies.stop_automatic()})
                        if live_manager is None:
                            raise Conflict('请先启动本机场次')
                        return self.respond(202, {'reply': replies.start_automatic(taobao, live_manager)})
                    if path == '/api/taobao/reply':
                        if set(value) != {'capture_id', 'comment_id'} or not isinstance(value['capture_id'], str) or type(value['comment_id']) is not int or value['comment_id'] < 1:
                            raise ProductError('请选择有效评论')
                        if live_manager is None:
                            raise Conflict('请先启动本机场次')
                        return self.respond(202, {'reply': replies.start(taobao, live_manager, value['capture_id'], value['comment_id'])})
                    if path in {'/api/taobao/login', '/api/taobao/start', '/api/taobao/stop'}:
                        if path.endswith('/start'):
                            if set(value) != {'live_id'}:
                                raise ProductError('淘宝采集请求字段无效')
                            return self.respond(202, {'capture': taobao.start(value['live_id'])})
                        if value:
                            raise ProductError('淘宝请求字段无效')
                        if path.endswith('/login'):
                            return self.respond(202, {'capture': taobao.login()})
                        return self.respond(200, {'capture': taobao.stop()})
                    live_active = live_manager is not None and live_manager.state()['status'] in ConsoleLive.active_states
                    if live_active and path in {'/api/config', '/api/products', '/api/products/select', '/api/avatars/select',
                                                '/api/voices/select', '/api/avatar-preparation/start', '/api/render/start'}:
                        raise Conflict('请先停止本机场次')
                    if path == '/api/live/start':
                        if set(value) != {'audio_device'} or type(value['audio_device']) is not int or value['audio_device'] < 0:
                            raise ProductError('请选择音频输出设备')
                        for manager in (avatar_manager, render_manager):
                            if manager is not None and (manager.state() or {}).get('status') == 'running':
                                raise Conflict('请先完成或取消视频任务')
                        if live_manager is None:
                            live_manager = ConsoleLive(tts(), store.directory)
                        return self.respond(202, {'session': live_manager.start(value['audio_device'])})
                    if path == '/api/live/rotation':
                        if set(value) != {'session_id', 'product_ids'} or not isinstance(value['session_id'], str):
                            raise ProductError('商品轮播字段无效')
                        ids = value['product_ids']
                        if not isinstance(ids, list) or len(ids) > 20 or not all(isinstance(item, str) and item for item in ids) or len(set(ids)) != len(ids):
                            raise ProductError('请选择最多20个不同商品')
                        if live_manager is None:
                            raise Conflict('暂无场次')
                        return self.respond(200, {'session': live_manager.configure_rotation(value['session_id'], ids)})
                    if path == '/api/live/control':
                        if set(value) != {'session_id', 'manual', 'revision'} or not isinstance(value['session_id'], str) or type(value['manual']) is not bool or type(value['revision']) is not int:
                            raise ProductError('场次控制字段无效')
                        if live_manager is None:
                            raise Conflict('暂无场次')
                        return self.respond(200, {'session': live_manager.set_manual(value['session_id'], value['manual'], value['revision'])})
                    if path in {'/api/live/stop', '/api/live/enqueue', '/api/live/insert', '/api/live/speak'}:
                        fields = {'session_id'} if path.endswith('/stop') else {'session_id', 'task_id'}
                        manual = path.endswith('/speak')
                        expected = fields | {'revision'} if manual else fields
                        if set(value) != expected or not all(isinstance(value[key], str) and value[key] for key in fields) or (manual and type(value['revision']) is not int):
                            raise ProductError('场次请求字段无效')
                        if live_manager is None:
                            raise Conflict('暂无场次')
                        if path.endswith('/stop'):
                            return self.respond(200, {'session': live_manager.stop(value['session_id'])})
                        live_manager.enqueue(value['session_id'], value['task_id'], priority=path.endswith('/insert'), manual_revision=value.get('revision'))
                        return self.respond(202, {'session': live_manager.state()})
                    if path == "/api/shutdown":
                        if value != {"confirm": True}:
                            raise ConfigError("退出请求无效")
                        self.respond(200, {"message": "控制台正在退出"})
                        threading.Thread(target=self.server.shutdown, daemon=True).start()
                        return
                    if path == "/api/config":
                        return self.respond(200, {"config": store.save(value), "message": "已保存；端口修改在下次启动生效"})
                    if path == "/api/preflight":
                        return self.respond(200, preflight(value))
                    if path == '/api/avatars/import':
                        if set(value)!={'source','name'} or not isinstance(value['source'],str):
                            raise AvatarError('形象导入字段无效')
                        avatar=AvatarStore(store.directory).import_prepared(value['source'],value['name'])
                        return self.respond(201,{'avatar':avatar})
                    if path == '/api/avatar-preparation/start':
                        if set(value)!={'source','name','resolution'}:
                            raise AvatarError('视频制作字段无效')
                        if tts_manager is not None and (tts_manager.state() or {}).get('status')=='running':
                            raise Conflict('正在合成语音，请完成或取消后再制作形象')
                        if render_manager is not None and (render_manager.state() or {}).get('status')=='running':
                            raise Conflict('正在合成视频，请完成或取消后再制作形象')
                        return self.respond(202,{'task':preparation().start(**value)})
                    if path == '/api/avatar-preparation/cancel':
                        if set(value)!={'task_id'} or not isinstance(value['task_id'],str):
                            raise AvatarError('视频制作取消字段无效')
                        manager=avatar_manager if avatar_manager is not None else preparation()
                        return self.respond(200,{'task':manager.cancel(value['task_id'])})
                    if path == '/api/avatars/select':
                        if set(value)!={'avatar_id'} or not isinstance(value['avatar_id'],str):
                            raise AvatarError('形象选择字段无效')
                        AvatarStore(store.directory).select(value['avatar_id'])
                        return self.respond(200,{'selected':value['avatar_id']})
                    if path in {'/api/voices/import','/api/voices/recorded'}:
                        field='source' if path.endswith('/import') else 'audio_base64'
                        if set(value)!={field,'transcript','name'} or not isinstance(value[field],str):
                            raise VoiceError('音色导入字段无效')
                        report=preflight(store.load())
                        if not report['runtime_root']: raise VoiceError('请先配置本机运行资源目录')
                        ffmpeg=Path(report['runtime_root'])/'_internal/env/ffmpeg/bin/ffmpeg.exe'
                        voices=VoiceStore(store.directory)
                        if field=='source':
                            voice=voices.import_audio(value['source'],value['transcript'],value['name'],ffmpeg)
                        else:
                            try: audio=base64.b64decode(value[field],validate=True)
                            except binascii.Error: raise VoiceError('录音数据格式无效') from None
                            voice=voices.import_recording(audio,value['transcript'],value['name'],ffmpeg)
                        return self.respond(201,{'voice':voice})
                    if path == '/api/voices/select':
                        if set(value)!={'voice_id'} or not isinstance(value['voice_id'],str):
                            raise VoiceError('音色选择字段无效')
                        VoiceStore(store.directory).select(value['voice_id'])
                        return self.respond(200,{'selected':value['voice_id']})
                    if path == '/api/tts/generate':
                        if set(value)!={'product_id','script_id','voice_id','speed','language','use_cache'}:
                            raise ProductError('TTS字段不完整')
                        if not all(isinstance(value[k],str) for k in ('product_id','script_id','voice_id')):
                            raise ProductError('TTS输入ID无效')
                        if avatar_manager is not None and (avatar_manager.state() or {}).get('status')=='running':
                            raise Conflict('正在制作形象，请完成或取消后再合成语音')
                        if render_manager is not None and (render_manager.state() or {}).get('status')=='running':
                            raise Conflict('正在合成视频，请完成或取消后再合成语音')
                        return self.respond(202,{'task':tts().start(**value)})
                    if path == '/api/render/start':
                        if set(value) not in ({'tts_task_id','avatar_id'},{'tts_task_id','avatar_id','render_profile'}):
                            raise ProductError('视频合成字段无效')
                        if avatar_manager is not None and (avatar_manager.state() or {}).get('status')=='running':
                            raise Conflict('正在制作形象，请完成或取消后再合成视频')
                        return self.respond(202,{'task':renders().start(**value)})
                    if path == '/api/render/cancel':
                        if set(value)!={'task_id'} or not isinstance(value['task_id'],str):
                            raise ProductError('视频取消字段无效')
                        manager=render_manager if render_manager is not None else renders()
                        return self.respond(200,{'task':manager.cancel(value['task_id'])})
                    if path == '/api/tts/cancel':
                        if set(value)!={'task_id'} or not isinstance(value['task_id'],str): raise ProductError('TTS取消字段无效')
                        return self.respond(200,{'task':tts().cancel(value['task_id'])})
                    if path == "/api/products":
                        allowed = {"title", "content", "product_index", "product_id", "version"}
                        if not {"title", "content", "product_index"} <= value.keys() or value.keys() - allowed:
                            raise ProductError("商品字段不完整或包含未知字段")
                        return self.respond(200, {"product": products().save(**value)})
                    if path == "/api/llm/generate":
                        if set(value) != {"product_id", "version", "instructions"} or not isinstance(value['product_id'], str):
                            raise ProductError("生成字段无效")
                        return self.respond(202, {"task":tasks().start(value['product_id'],value['version'],value['instructions'])})
                    if path == "/api/llm/cancel":
                        if set(value) != {"task_id"}: raise ProductError("取消字段无效")
                        return self.respond(200, {"task":tasks().cancel(value['task_id'])})
                    if path == "/api/products/select":
                        if set(value) != {"product_id"} or not isinstance(value["product_id"], str):
                            raise ProductError("请选择有效商品")
                        products().select(value["product_id"])
                        return self.respond(200, {"selected": value["product_id"]})
                    if path == "/api/scripts":
                        if not {'snapshot','text'} <= value.keys() or value.keys()-{'snapshot','text','parent_script_id'}:
                            raise ProductError("话术字段不完整")
                        script_id = products().add_script(value["snapshot"], value["text"],parent_script_id=value.get('parent_script_id'))
                        return self.respond(201, {"id": script_id})
                    if path == '/api/scripts/select':
                        if set(value)!={'product_id','script_id'} or not all(isinstance(v,str) for v in value.values()):
                            raise ProductError('话术选择字段无效')
                        products().select_script(value['product_id'],value['script_id'])
                        return self.respond(200,{'selected':value['script_id']})
                return self.respond(404, {"error": "接口不存在"})
            except Conflict as error:
                self.respond(409, {"error": str(error)})
            except sqlite3.Error:
                self.respond(503, {"error": "商品数据库操作失败，请检查文件与权限；原数据未重置"})
            except (ValueError, UnicodeError, OSError) as error:
                self.respond(400, {"error": str(error)})

    server = ConsoleServer(("127.0.0.1", configured_port if port is None else port), Handler)
    server.daemon_threads = True
    server.cleanup_tasks = cleanup
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="数字人本地控制台")
    parser.add_argument("--data-directory", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--tts-engine", choices=("indextts", "zipvoice", "omnivoice"), default="indextts")
    parser.add_argument("--tts-model-root", type=Path)
    args = parser.parse_args(argv)
    store = ConfigStore(args.data_directory)
    store.directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=store.directory / "console.log", encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    instance = InstanceLock(store.directory)
    try:
        instance.__enter__()
        server = create_server(store, args.port, tts_engine=args.tts_engine,
                               tts_model_root=args.tts_model_root)
    except OSError as error:
        instance.__exit__()
        logging.error("启动失败：%s", error)
        print("控制台启动失败，请检查端口是否占用：%s" % error, flush=True)
        return 1
    print("http://127.0.0.1:%d/" % server.server_port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        instance.__exit__()
        logging.info("控制台已关闭")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
