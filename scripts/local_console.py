"""Own loopback console: python -m scripts.local_console --data-directory PATH."""
import argparse
import base64
import binascii
from collections import Counter
import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import socket
import sqlite3
import threading
from urllib.parse import urlsplit, parse_qs

from scripts.local_console_config import ConfigError, ConfigStore, preflight, shop_data_directory
from scripts.product_store import ProductStore, Conflict, ProductError
from scripts.voice_store import VoiceStore, VoiceError
from scripts.avatar_store import AvatarStore, AvatarError
from scripts.console_live import ConsoleLive
from scripts.console_taobao import ConsoleTaobao
from scripts.console_comment_reply import ConsoleCommentReply

WEB = Path(__file__).parent / "local-console"
ACCESS_ROLES = ('viewer', 'operator', 'admin')
ACCESS_ACCOUNT = re.compile(r'[a-z0-9][a-z0-9_-]{0,39}')
AUTHORIZATION_AUDIT_MAX_BYTES = 4 * 1024 * 1024
OPERATOR_POST_PATHS = {
    '/api/live/start', '/api/live/video-seek', '/api/live/rotation', '/api/live/control',
    '/api/live/stop', '/api/live/enqueue', '/api/live/insert', '/api/live/speak',
    '/api/live/advice/acknowledge', '/api/live/advice/revoke',
    '/api/taobao/goods', '/api/taobao/explain', '/api/taobao/auto-reply',
    '/api/taobao/reply', '/api/taobao/login', '/api/taobao/start', '/api/taobao/stop',
    '/api/shutdown', '/api/preflight',
}


def role_allows_post(role, path):
    if role == 'admin':
        return True
    if role == 'operator':
        return path in OPERATOR_POST_PATHS
    return path == '/api/preflight'


def valid_access_account(value):
    return isinstance(value, str) and ACCESS_ACCOUNT.fullmatch(value) is not None


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


def reply_question_key(reply):
    return reply['product_id'], ' '.join(reply['question'].split())


def browser_metrics(values):
    """Encode counts outside the JavaScript safe integer range losslessly."""
    return {key: str(value) if type(value) is int and value >= 2**53 else value
            for key, value in values.items()}


def live_advice(session, repeated_questions=()):
    underrun = session.get('device_underrun')
    if session['status'] == 'failed' and underrun is not None:
        return [{
            'code': 'device_underrun',
            'evidence': '本机音视频设备队列欠载，场次输出已停止',
            'recommendation': '检查音频输出设备和本机推理负载，再重新启动场次',
            'context': {'occurred_at': session.get('ended_at'), 'next_frame': underrun.get('next_frame')},
        }]
    if session['status'] != 'running':
        return []
    advice = [
        {'code': field, 'evidence': session[field], 'recommendation': recommendation}
        for field, recommendation in (
            ('rotation_error', '检查故障原因并核对轮播配置，再决定是否重试'),
            ('insert_error', '核对插播素材与语音输出，再决定是否重试'),
        )
        if session.get(field)
    ]
    if session.get('automatic_queue_full') is True:
        advice.append({'code': 'automatic_queue_full',
                       'evidence': f"普通口播队列已满，待播 {session['pending']} 条",
                       'recommendation': '等待队列释放后再添加口播'})
    if session.get('silent_speech'):
        advice.append({'code': 'silent_speech', 'evidence': '口播输出连续至少 5 秒为零音频',
                       'recommendation': '核对当前话术生成的语音及本机音频输出',
                       'context': session['silent_speech']})
    if session.get('shift_waiting_for_boundary'):
        shift = session['shift_waiting_for_boundary']
        advice.append({'code': 'shift_waiting_for_boundary',
                       'evidence': f"当前班次已到设定时长（{shift['duration_seconds']:g} 秒），尚未切品",
                       'recommendation': '等待当前商品讲解结束后切换，若持续未切换请检查轮播状态',
                       'context': shift})
    if session.get('rotation_stock_evidence'):
        stock = session['rotation_stock_evidence']
        advice.append({'code': 'rotation_stock_zero', 'evidence': f"轮播商品版本的已核对库存为 0，来源 {stock['source']}",
                       'recommendation': '确认当前可售库存，再决定是否调整讲解或切品', 'context': stock})
    for item in advice:
        if item['code'] == 'rotation_error' and session.get('rotation_fault'):
            item['context'] = session['rotation_fault']
    for question in repeated_questions:
        advice.append({'code': 'repeated_question', 'evidence': f"同商品重复提问 {question['occurrences']} 次：{question['question']}",
                       'recommendation': '核对商品事实后，可补讲或补充 FAQ',
                       'context': {'product_id': question['product_id'], 'occurred_at': question['last_queued_at'],
                                   'task_id': question['task_id']}})
    return advice


def create_server(store, port=None, *, tts_engine="indextts", tts_model_root=None, shop_id=None,
                  access_role='admin', access_account='local'):
    if access_role not in ACCESS_ROLES:
        raise ValueError('控制台访问角色无效')
    if not valid_access_account(access_account):
        raise ValueError('控制台账号编号无效')
    token = secrets.token_urlsafe(32)
    lock = threading.RLock()
    audit_lock = threading.Lock()
    def authorization_audit(path, allowed):
        from datetime import datetime, timezone
        event = {
            'occurred_at': datetime.now(timezone.utc).isoformat(),
            'shop_id': shop_id, 'account_id': access_account, 'access_role': access_role,
            'path': path, 'allowed': allowed,
        }
        with audit_lock:
            store.directory.mkdir(parents=True, exist_ok=True)
            path = store.directory / 'authorization-audit.jsonl'
            if path.is_file() and path.stat().st_size >= AUTHORIZATION_AUDIT_MAX_BYTES:
                rotated = store.directory / 'authorization-audit.jsonl.1'
                rotated.unlink(missing_ok=True)
                path.replace(rotated)
            with path.open('a', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n')
    product_lock = threading.Lock()
    product_store = None
    preparation_template_store = None
    def products():
        nonlocal product_store
        with product_lock:
            if product_store is None:
                product_store = ProductStore(store.directory)
            return product_store
    def preparation_templates():
        nonlocal preparation_template_store
        with product_lock:
            if preparation_template_store is None:
                from scripts.preparation_template_store import PreparationTemplateStore
                root = store.directory.parent.parent if shop_id is not None else store.directory
                preparation_template_store = PreparationTemplateStore(root)
            return preparation_template_store
    def current_live_advice(session):
        if session['status'] != 'running' or not session.get('id'):
            return live_advice(session)
        from time import time
        return live_advice(session, products().recent_repeated_live_questions(session['id'], time() - 300))
    task_manager = None
    tts_manager = None
    avatar_manager = None
    render_manager = None
    sticker_manager = None
    live_manager = None
    taobao = ConsoleTaobao(store.directory)
    replies = ConsoleCommentReply()
    tasks_closed = False
    def live_label():
        status = live_manager.state()['status'] if live_manager else 'idle'
        return {'idle': '未启动', 'preparing': '准备中', 'running': '本机输出中',
                'stopping': '停止中', 'stopped': '已停止', 'failed': '输出失败'}[status]
    def stickers():
        nonlocal sticker_manager
        with lock:
            if tasks_closed: raise ProductError('控制台正在退出')
            if sticker_manager is None:
                from recovered.main import Api
                sticker_manager = Api.__new__(Api)
                sticker_manager.runtime_dir = store.directory
                sticker_manager.config = {}
                sticker_manager._get_ip_agent_base_dir = lambda: str(store.directory / 'ip_agent_projects')
            return sticker_manager
    def sticker_result(result):
        if not isinstance(result, dict): raise ProductError('贴片项目返回无效')
        if result.get('error'): raise ProductError(result['error'])
        if result.get('status') == 'error': raise ProductError(result.get('message') or '贴片项目操作失败')
        return result
    def ip_result(result):
        if not isinstance(result, dict): raise ProductError('IP 项目返回无效')
        if result.get('code') in ('publish_in_progress', 'publish_outcome_unknown'):
            raise Conflict(result.get('message') or result.get('error') or 'IP 发布状态冲突')
        if result.get('error'): raise ProductError(result['error'])
        if result.get('status') == 'error': raise ProductError(result.get('message') or 'IP 项目操作失败')
        return result
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
            if sticker_manager is not None:
                _, jobs = sticker_manager._live_sticker_job_state()
                for event in tuple(jobs.values()): event.set()
                _, cloud_jobs = sticker_manager._cloud_dh_job_state()
                for event in tuple(cloud_jobs.values()): event.set()
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

        def respond(self, status, body, content_type="application/json; charset=utf-8", *, attachment=None):
            content = json.dumps(body, ensure_ascii=False).encode("utf-8") if isinstance(body, dict) else body
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                if attachment:
                    self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
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
                    session = live_manager.state() if live_manager else {'status': 'idle'}
                    advice = current_live_advice(session)
                    acknowledged = []
                    if advice and session.get('id'):
                        active = [entry['advice'] for entry in products().live_advice_acknowledgments(session['id'])
                                  if entry['revoked_at'] is None]
                        acknowledged = [item for item in advice if item in active]
                    return self.respond(200, {'session': session, 'advice': advice, 'acknowledged': acknowledged})
                if path == '/api/live/advice':
                    session = live_manager.state() if live_manager else {'status': 'idle'}
                    return self.respond(200, {'session_id': session.get('id'), 'advice': current_live_advice(session)})
                if path == '/api/live/history':
                    return self.respond(200, {'sessions': products().recent_live_sessions()})
                if path == '/api/live/control/events':
                    sessions = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get('session_id', [])
                    if len(sessions) != 1 or not 1 <= len(sessions[0]) <= 64:
                        raise ProductError('场次无效')
                    return self.respond(200, {'events': products().live_control_events(sessions[0])})
                if path == '/api/live/compare':
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if (set(query) != {'baseline', 'trial'}
                            or any(len(values) != 1 or not 1 <= len(values[0]) <= 64 for values in query.values())
                            or query['baseline'] == query['trial']):
                        raise ProductError('请选择两个不同场次')
                    data = products()
                    comparison = {}
                    for role in ('baseline', 'trial'):
                        report = data.live_session_report(query[role][0])
                        session = report['session']
                        if session['ended_at'] is None:
                            raise ProductError('请选择已结束的场次')
                        started_at = session['started_at']
                        duration = None if started_at is None else session['ended_at'] - started_at
                        completed = sum(item['completed_segments'] for item in report['products'])
                        queued_replies = report['queued_replies']
                        unqueued_replies = report['unqueued_replies']
                        question_counts = Counter(map(reply_question_key, (*queued_replies, *unqueued_replies)))
                        verdicts = {verdict: sum(item['verdict'] == verdict for item in queued_replies)
                                    for verdict in ('correct', 'incorrect', 'uncertain')}
                        review_times = [item['review_seconds'] for item in queued_replies if item['review_seconds'] is not None]
                        comparison[role] = {
                            'session': session,
                            'duration_seconds': duration if duration and duration > 0 else None,
                            'completed_segments': completed,
                            'completed_segments_per_minute': completed * 60 / duration
                            if duration and duration > 0 else None,
                            'rotation_faults': len(report['rotation_faults']),
                            'played_replies': sum(item['played_at'] is not None for item in queued_replies),
                            'unqueued_questions': len(unqueued_replies),
                            'repeated_question_groups': sum(count > 1 for count in question_counts.values()),
                            'repeat_question_occurrences': sum(count - 1 for count in question_counts.values()),
                            'reply_review': {**verdicts, 'unreviewed': len(queued_replies) - sum(verdicts.values()),
                                             'timed': len(review_times), 'seconds': sum(review_times) if review_times else None},
                            'products': report['products'],
                            'video_counters': report['video_counters'],
                            'lineup_baseline': report['lineup_baseline'],
                            'preparation_applications': data.live_preparation_applications(session['session_id']),
                            'observed_product_order': (
                                [report['products'][0]['product_id']] +
                                [item['product_id'] for item in report['observed_product_switches']]
                                if report['products'] else []
                            ),
                        }
                    return self.respond(200, {**comparison, 'conclusion': 'uncertain',
                                              'missing': ['audience', 'traffic', 'promotion', 'refund_lag']})
                if path in {'/api/live/report', '/api/live/review', '/api/live/improvements'}:
                    sessions = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get('session_id', [])
                    if len(sessions) != 1 or not 1 <= len(sessions[0]) <= 64:
                        raise ProductError('场次无效')
                    if path == '/api/live/improvements':
                        return self.respond(200, {'tasks': products().live_improvements(sessions[0])})
                    current = live_manager.state() if path == '/api/live/report' and live_manager is not None else {}
                    report = products().live_session_report(sessions[0])
                    if (current.get('id') == sessions[0] and current.get('status') == 'running'
                            and report['session']['status'] == 'running'):
                        report['session']['frames'] = max(report['session']['frames'], current['frames'])
                    if path == '/api/live/review':
                        questions = {}
                        for reply in report['queued_replies']:
                            key = reply_question_key(reply)
                            group = questions.setdefault(key, {
                                'product_id': key[0], 'question': key[1], 'evidence': [],
                            })
                            group['evidence'].append({name: reply[name] for name in
                                                      ('task_id', 'product_version', 'queued_at', 'played_at')})
                        repeated_questions = [
                            {**group, 'recommendation': '核对现有话术和 FAQ 是否覆盖该问题，再决定是否补充'}
                            for group in questions.values() if len(group['evidence']) > 1
                        ]
                        return self.respond(200, {
                            'session_id': sessions[0], 'missing': report['missing'],
                            'repeated_questions': repeated_questions,
                            'replies_without_playback_record': [
                                {name: reply[name] for name in
                                 ('task_id', 'product_id', 'product_version', 'question', 'queued_at')}
                                for reply in report['queued_replies'] if reply['played_at'] is None
                            ],
                            'unqueued_replies': report['unqueued_replies'],
                            'findings': [{
                                'evidence': {'event_id': fault['event_id'], 'occurred_at': fault['occurred_at']},
                                'fact': fault['reason'],
                                'recommendation': '开播前复测该故障并记录复测结果',
                            } for fault in report['rotation_faults']],
                        })
                    report['advice_acknowledgments'] = products().live_advice_acknowledgments(sessions[0])
                    report['advice_actions'] = products().live_advice_actions(sessions[0])
                    report['preparation_applications'] = products().live_preparation_applications(sessions[0])
                    return self.respond(200, report)
                if path in {'/api/live/content-source', '/api/live/content-draft', '/api/live/content-schedule'}:
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if (set(query) != {'session_id', 'task_id'}
                            or any(len(values) != 1 or not 1 <= len(values[0]) <= 64 for values in query.values())):
                        raise ProductError('需要有效的场次和口播任务编号')
                    source = products().live_content_source(query['session_id'][0], query['task_id'][0])
                    if path == '/api/live/content-schedule':
                        return self.respond(200, {'schedule': products().live_content_schedule(
                            source['session_id'], source['task_id']), 'facts_review': source['facts_review']})
                    if path == '/api/live/content-draft':
                        saved_body = products().live_content_draft_body(source['session_id'], source['task_id'])
                        if products().live_content_draft_withdrawn(source['session_id'], source['task_id']):
                            return self.respond(200, {'draft': {'saved_body': saved_body, 'editable': False,
                                                                 'withdrawn': True}})
                        if source['facts_review'] != 'version_current' or source['segment'] is None:
                            if saved_body is not None:
                                return self.respond(200, {'draft': {'saved_body': saved_body, 'editable': False}})
                            raise Conflict('商品事实或片段来源需要重新核对')
                        title = source['product_snapshot']['title']
                        start, end = source['sample_start'], source['sample_end']
                        subtitle = None
                        if start is not None and end is not None and 0 <= start < end:
                            milliseconds = (end - start + 23) // 24
                            seconds, fraction = divmod(milliseconds, 1000)
                            minutes, seconds = divmod(seconds, 60)
                            hours, minutes = divmod(minutes, 60)
                            timestamp = f'{hours:02}:{minutes:02}:{seconds:02},{fraction:03}'
                            caption = '\n'.join(line for line in source['segment']['content'].splitlines() if line.strip())
                            subtitle = f'1\n00:00:00,000 --> {timestamp}\n{caption}\n'
                        return self.respond(200, {'draft': {
                            'saved_body': saved_body, 'editable': True,
                            'title': f'{title}讲解片段', 'cover_text': title,
                            'narration': source['segment']['content'],
                            'subtitle_srt': subtitle,
                            'language': (source['speech_provenance'] or {}).get('language'),
                            'source': {key: source[key] for key in
                                       ('session_id', 'task_id', 'product_id', 'product_version', 'script_id',
                                        'segment_index', 'voice_id', 'sample_start', 'sample_end')},
                            'speaker_role': source['segment']['type'],
                            'speech_provenance': source['speech_provenance'],
                            **products().live_content_timings(
                                source['session_id'], source['task_id']),
                        }})
                    source['has_saved_draft'] = products().live_content_draft_body(
                        source['session_id'], source['task_id']) is not None
                    return self.respond(200, {'source': source})
                if path == '/api/live/content-audio':
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if (set(query) != {'session_id', 'task_id'}
                            or any(len(values) != 1 or not 1 <= len(values[0]) <= 64 for values in query.values())):
                        raise ProductError('需要有效的场次和口播任务编号')
                    from scripts.media_http import serve_file
                    return serve_file(self, products().live_content_audio_path(
                        query['session_id'][0], query['task_id'][0]), 'audio/wav')
                if path == '/api/live/rotation/events':
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    sessions = query.get('session_id', [])
                    cursors = query.get('after', ['0'])
                    filters = {}
                    for name in ('product_id', 'task_id'):
                        if name in query:
                            values = query[name]
                            if len(values) != 1 or not 1 <= len(values[0]) <= 64:
                                raise ProductError('商品或任务筛选条件无效')
                            filters[name] = values[0]
                    if (len(sessions) != 1 or not 1 <= len(sessions[0]) <= 64 or len(cursors) != 1
                            or not cursors[0].isascii() or not cursors[0].isdigit() or len(cursors[0]) > 19
                            or int(cursors[0]) >= 2**63):
                        raise ProductError('场次或轮播记录游标无效')
                    after = int(cursors[0])
                    data = products()
                    events = data.rotation_events(sessions[0], after=after, **filters)
                    return self.respond(200, {
                        'session': data.live_session_record(sessions[0]), 'events': events,
                        'next_cursor': events[-1]['cursor'] if events else after,
                    })
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
                    return self.respond(200, {"token": token, "tts_engine": tts_engine, "shop_id": shop_id,
                                              "access_role": access_role, "account_id": access_account})
                if path == '/api/voices':
                    voices=VoiceStore(store.directory)
                    return self.respond(200,{'voices':voices.list(),'selected':voices.selected()})
                if path == '/api/avatars':
                    avatars=AvatarStore(store.directory)
                    return self.respond(200,{'avatars':avatars.list(),'selected':avatars.selected()})
                if path == '/api/stickers':
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if not query:
                        return self.respond(200, sticker_result(stickers().get_all_live_sticker_projects()))
                    ids = query.get('project_id', [])
                    if set(query) != {'project_id'} or len(ids) != 1 or not 1 <= len(ids[0]) <= 64:
                        raise ProductError('贴片项目编号无效')
                    return self.respond(200, sticker_result(stickers().get_live_sticker_project(ids[0])))
                if path == '/api/cloud-dh':
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if not query:
                        return self.respond(200, sticker_result(stickers().get_all_cloud_dh_projects()))
                    ids = query.get('project_id', [])
                    if set(query) != {'project_id'} or len(ids) != 1 or not 1 <= len(ids[0]) <= 64:
                        raise ProductError('云数字人项目编号无效')
                    return self.respond(200, sticker_result(stickers().get_cloud_dh_project(ids[0])))
                if path == '/api/ip-agent':
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if not query:
                        return self.respond(200, ip_result(stickers().get_all_ip_agent_projects()))
                    ids = query.get('project_id', [])
                    if set(query) != {'project_id'} or len(ids) != 1 or not 1 <= len(ids[0]) <= 80:
                        raise ProductError('IP 项目编号无效')
                    return self.respond(200, ip_result(stickers().get_ip_agent_project(ids[0])))
                if path == '/api/cloud-dh/media':
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if set(query) != {'project_id', 'kind'} or any(len(value) != 1 for value in query.values()):
                        raise ProductError('云数字人媒体请求无效')
                    project_id, kind = query['project_id'][0], query['kind'][0]
                    if not 1 <= len(project_id) <= 64 or kind not in ('avatar', 'audio', 'video'):
                        raise ProductError('云数字人媒体请求无效')
                    stickers()._load_cloud_dh_project(project_id)
                    asset = Path(stickers()._get_cloud_dh_output_paths(project_id)[kind])
                    from scripts.media_http import serve_file
                    return serve_file(self, asset, {'avatar':'image/png','audio':'audio/wav','video':'video/mp4'}[kind])
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
                if path in {'/api/render/video', '/api/render/subtitle', '/api/render/cover'}:
                    ids=parse_qs(urlsplit(self.path).query).get('task_id',[])
                    if len(ids)!=1: raise ProductError('请选择有效视频任务')
                    manager=render_manager if render_manager is not None else renders()
                    if path == '/api/render/subtitle':
                        subtitle = manager.subtitle(ids[0]).encode('utf-8')
                        return self.respond(200, subtitle, 'application/x-subrip; charset=utf-8',
                                            attachment='avatar-subtitles.srt')
                    from scripts.media_http import serve_file
                    if path == '/api/render/cover':
                        return serve_file(self,manager.cover_path(ids[0]),'image/jpeg')
                    return serve_file(self,manager.video_path(ids[0]),'video/mp4')
                if path == '/api/tts/audio':
                    ids=parse_qs(urlsplit(self.path).query).get('task_id',[])
                    if len(ids)!=1: raise ProductError('音频任务参数无效')
                    return self.respond(200,tts().audio(ids[0]),'audio/wav')
                if path == '/api/voices/audio':
                    ids=parse_qs(urlsplit(self.path).query).get('id',[])
                    if len(ids)!=1: raise VoiceError('请选择音色')
                    return self.respond(200,VoiceStore(store.directory).audio_path(ids[0]).read_bytes(),'audio/wav')
                if path == "/api/live/preparation":
                    return self.respond(200, products().live_preparation())
                if path == "/api/live/preparation/baseline":
                    return self.respond(200, {'baseline': products().live_lineup_baseline()})
                if path == "/api/live/preparation/package":
                    return self.respond(200, products().build_live_preparation())
                if path == "/api/preparation-templates":
                    return self.respond(200, {'templates': preparation_templates().list()})
                if path == "/api/products/after-sales/compare":
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if (set(query) != {'product_id', 'source', 'baseline_start', 'baseline_end', 'trial_start', 'trial_end'}
                            or any(len(values) != 1 or not values[0] for values in query.values())):
                        raise ProductError('请选择商品、来源和两个售后统计窗口')
                    return self.respond(200, {'comparison': products().compare_after_sales(
                        **{name: values[0] for name, values in query.items()})})
                if path == "/api/products/after-sales":
                    ids = parse_qs(urlsplit(self.path).query).get('product_id', [])
                    if len(ids) != 1 or not 1 <= len(ids[0]) <= 64:
                        raise ProductError('请选择商品')
                    return self.respond(200, {'reports': products().after_sales(ids[0])})
                if path in {"/api/sourcing/trial", "/api/sourcing/decision", "/api/sourcing/decision/history"}:
                    ids = parse_qs(urlsplit(self.path).query).get('candidate_id', [])
                    if len(ids) != 1 or not 1 <= len(ids[0]) <= 64:
                        raise ProductError('请选择采购候选')
                    if path.endswith('/decision'):
                        return self.respond(200, {'decision': products().sourcing_decision(ids[0])})
                    if path.endswith('/history'):
                        return self.respond(200, {'decisions': products().sourcing_decision_archive(ids[0])})
                    return self.respond(200, {'trial': products().sourcing_trial(ids[0])})
                if path == "/api/promotion/compare":
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if (set(query) != {'product_id', 'source', 'campaign', 'asset',
                                       'baseline_start', 'baseline_end', 'trial_start', 'trial_end'}
                            or any(len(values) != 1 or not values[0] for values in query.values())):
                        raise ProductError('请选择投放对象和两个账单窗口')
                    return self.respond(200, {'comparison': products().compare_promotion_spend(
                        **{key: values[0] for key, values in query.items()})})
                if path == "/api/promotion/plans/actions":
                    ids = parse_qs(urlsplit(self.path).query).get('plan_id', [])
                    if len(ids) != 1 or not 1 <= len(ids[0]) <= 64:
                        raise ProductError('请选择投放方案')
                    return self.respond(200, {'actions': products().promotion_plan_actions(ids[0])})
                if path in {"/api/promotion/spend", "/api/promotion/plans"}:
                    ids = parse_qs(urlsplit(self.path).query).get('product_id', [])
                    if len(ids) != 1 or not 1 <= len(ids[0]) <= 64:
                        raise ProductError('请选择投放商品')
                    if path.endswith('/plans'):
                        return self.respond(200, {'plans': products().promotion_plans(ids[0])})
                    return self.respond(200, {'records': products().promotion_spend(ids[0])})
                if path == "/api/sourcing/candidates":
                    return self.respond(200, {'candidates': products().sourcing_candidates()})
                if path == "/api/products/guide":
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    ids = query.get('product_id', [])
                    names = [name.strip() for name in query.get('fact', [])]
                    if (set(query) != {'product_id', 'fact'} or not 1 <= len(ids) <= 10
                            or len(ids) != len(set(ids)) or any(not 1 <= len(item) <= 64 for item in ids)
                            or not 1 <= len(names) <= 12 or len(names) != len(set(names))
                            or any(not 1 <= len(name) <= 100 for name in names)):
                        raise ProductError('请选择商品和需要比较的商品事实')
                    return self.respond(200, {'products': products().compare_product_facts(ids, names)})
                if path == "/api/products/selection-evidence":
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    fields = {'source', 'scope', 'period_start', 'period_end'}
                    if query and (set(query) != fields or any(len(values) != 1 or not values[0]
                                                               for values in query.values())):
                        raise ProductError('请填写经营数据来源、口径和日期区间')
                    data = products()
                    candidates = data.product_selection_evidence()
                    if not query:
                        return self.respond(200, {'products': candidates})
                    scope = {key: values[0] for key, values in query.items()}
                    for candidate in candidates:
                        try:
                            candidate['business_metrics'] = data.summarize_business_metrics(candidate['product_id'], **scope)
                        except ProductError as error:
                            candidate['business_metrics'] = None
                            candidate['business_metrics_gap'] = str(error)
                        if candidate['business_metrics'] is not None:
                            refunds = candidate['business_metrics']['refunds']
                            orders = candidate['business_metrics']['orders']
                            if refunds is not None and refunds > 0:
                                candidate['refund_review'] = (
                                    '窗口内退款多于订单，请核对退款归属及滞后窗口'
                                    if orders is not None and refunds > orders
                                    else '窗口内有退款，请核对退款原因及对应订单后再决定排品'
                                )
                            candidate['business_metrics'] = browser_metrics(candidate['business_metrics'])
                    return self.respond(200, {'products': candidates, 'business_metrics_scope': scope})
                if path == "/api/products":
                    data = products()
                    return self.respond(200, {"products": data.list(), "selected": data.selected()})
                if path == "/api/products/business-metrics":
                    ids = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get("product_id", [])
                    if len(ids) != 1 or not ids[0]:
                        raise ProductError("请选择有效商品")
                    return self.respond(200, {"records": list(map(browser_metrics, products().business_metrics(ids[0])))})
                if path == "/api/products/business-metrics/summary":
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    fields = {"product_id", "source", "scope", "period_start", "period_end"}
                    if set(query) != fields or any(len(values) != 1 or not values[0] for values in query.values()):
                        raise ProductError("请选择商品、数据来源、统计口径和日期")
                    summary = products().summarize_business_metrics(**{key: values[0] for key, values in query.items()})
                    return self.respond(200, {"summary": browser_metrics(summary)})
                if path == "/api/llm/state":
                    from scripts.console_llm import status
                    return self.respond(200, {**status(), "task":tasks().state()})
                if path == "/api/scripts":
                    query = parse_qs(urlsplit(self.path).query)
                    ids = query.get("product_id", [])
                    if len(ids) != 1:
                        raise ProductError("请选择商品")
                    data=products()
                    from recovered.slice_content import slice_content

                    scripts = data.scripts(ids[0])
                    for script in scripts:
                        segments = slice_content(script['text'])
                        if any(segment['type'] in {'assistant', 'pause'} for segment in segments):
                            script['segments'] = segments
                    return self.respond(200, {"scripts": scripts, 'selected': data.selected_script(ids[0])})
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
                allowed = role_allows_post(access_role, path)
                if path != '/api/preflight':
                    authorization_audit(path, allowed)
                if not allowed:
                    return self.respond(403, {"error": "当前账号角色无权执行此操作", "access_role": access_role})
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
                                                '/api/voices/select', '/api/avatar-preparation/start', '/api/render/start',
                                                '/api/live/content-render'}:
                        raise Conflict('请先停止本机场次')
                    if path == '/api/live/start':
                        if set(value) - {'audio_device', 'rotation_language', 'assistant_voice_id', 'video_path', 'video_backend', 'camera_device', 'rtmp_url'} or type(value.get('audio_device')) is not int or value['audio_device'] < 0:
                            raise ProductError('请选择音频输出设备')
                        if 'video_path' in value:
                            if set(value) - {'audio_device', 'video_path', 'video_backend'}:
                                raise ProductError('本地视频模式的开播字段无效')
                            if value.get('video_backend', 'cuda') not in ('cuda', 'tensorrt'):
                                raise ProductError('本地视频推理后端无效')
                        elif 'video_backend' in value:
                            raise ProductError('请选择本地驱动视频')
                        rtmp_url = value.get('rtmp_url')
                        if 'rtmp_url' in value:
                            try:
                                if not isinstance(rtmp_url, str):
                                    raise ValueError
                                rtmp_url = rtmp_url.strip()
                                target = urlsplit(rtmp_url)
                                if (target.scheme not in ('rtmp', 'rtmps') or not target.hostname
                                        or target.port == 0 or any(char.isspace() or ord(char) < 32 for char in rtmp_url)):
                                    raise ValueError
                            except ValueError:
                                raise ProductError('RTMP 输入地址无效') from None
                        assistant_voice_id = value.get('assistant_voice_id')
                        camera_device = value.get('camera_device')
                        if camera_device is not None and (
                                not isinstance(camera_device, str) or not 1 <= len(camera_device.strip()) <= 256
                                or '\x00' in camera_device):
                            raise ProductError('虚拟摄像头设备名称无效')
                        if assistant_voice_id is not None and (not isinstance(assistant_voice_id, str) or not assistant_voice_id):
                            raise ProductError('助播音色无效')
                        language = value.get('rotation_language', 'zh-CN')
                        if language != 'zh-CN' and (tts_engine != 'omnivoice' or language not in ('en-US', 'ms-MY', 'vi-VN')):
                            raise ProductError('当前语音引擎不支持所选轮播语言')
                        for manager in (avatar_manager, render_manager):
                            if manager is not None and (manager.state() or {}).get('status') == 'running':
                                raise Conflict('请先完成或取消视频任务')
                        if live_manager is None:
                            live_manager = ConsoleLive(tts(), store.directory)
                        if 'video_path' in value:
                            return self.respond(202, {'session': live_manager.start_video(
                                value['audio_device'], value['video_path'], backend=value.get('video_backend', 'cuda'),
                            )})
                        return self.respond(202, {'session': live_manager.start(
                            value['audio_device'], language=language, assistant_voice_id=assistant_voice_id,
                            **({'camera_device': camera_device.strip()} if camera_device is not None else {}),
                            **({'rtmp_url': rtmp_url} if rtmp_url is not None else {}),
                        )})
                    if path == '/api/live/video-seek':
                        if set(value) != {'session_id', 'position_ms'} or not isinstance(value['session_id'], str):
                            raise ProductError('视频跳转字段无效')
                        if live_manager is None:
                            raise Conflict('暂无场次')
                        return self.respond(202, {'session': live_manager.seek_video(value['session_id'], value['position_ms'])})
                    if path == '/api/live/rotation':
                        if (set(value) - {'session_id', 'product_ids', 'shift_durations', 'shift_voice_ids', 'preparation'}
                                or not isinstance(value.get('session_id'), str)):
                            raise ProductError('商品轮播字段无效')
                        ids = value.get('product_ids')
                        if not isinstance(ids, list) or len(ids) > 20 or not all(isinstance(item, str) and item for item in ids) or len(set(ids)) != len(ids):
                            raise ProductError('请选择最多20个不同商品')
                        if live_manager is None:
                            raise Conflict('暂无场次')
                        prepared_rotation = value.get('preparation')
                        expected_items = None
                        current = None
                        if prepared_rotation is not None:
                            if (not isinstance(prepared_rotation, dict) or set(prepared_rotation) != {'revision', 'items'}
                                    or not isinstance(prepared_rotation['revision'], str)):
                                raise ProductError('准备包轮播配置无效')
                            current = products().live_preparation_rotation(
                                prepared_rotation['revision'], include_improvements=True)
                            expected_items = [
                                {key: item[key] for key in ('product_id', 'product_version', 'script_id')}
                                for item in current['items']
                            ]
                            if ids != [item['product_id'] for item in expected_items] or prepared_rotation['items'] != expected_items:
                                raise Conflict('准备包轮播配置已变化，请重新核对')
                        return self.respond(200, {'session': live_manager.configure_rotation(
                            value['session_id'], ids, shift_durations=value.get('shift_durations'),
                            shift_voice_ids=value.get('shift_voice_ids'),
                            expected_items=expected_items,
                            **({'preparation': current} if current is not None else {}),
                        )})
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
                    if path == '/api/stickers/create':
                        if set(value) != {'name'} or not isinstance(value['name'], str) or len(value['name']) > 100:
                            raise ProductError('贴片项目名称无效')
                        return self.respond(201, sticker_result(stickers().create_live_sticker_project(value['name'])))
                    if path == '/api/stickers/update':
                        if set(value) != {'project_id', 'data'} or not isinstance(value['project_id'], str) or not isinstance(value['data'], dict):
                            raise ProductError('贴片项目保存字段无效')
                        allowed = {'name', 'product_name', 'product_price', 'product_selling_points',
                                   'product_content', 'product_item_id', 'product_pic', 'background_prompt',
                                   'foreground_prompt', 'cover_prompt', 'room_title', 'room_titles'}
                        if set(value['data']) - allowed:
                            raise ProductError('贴片项目包含不可修改字段')
                        return self.respond(200, sticker_result(stickers().update_live_sticker_project(
                            value['project_id'], value['data'])))
                    if path == '/api/stickers/prompts':
                        if set(value) != {'project_id', 'product'} or not isinstance(value['project_id'], str) or not isinstance(value['product'], dict):
                            raise ProductError('贴片提示词字段无效')
                        return self.respond(200, sticker_result(stickers().generate_live_sticker_prompts(value)))
                    if path == '/api/stickers/generate':
                        required = {'project_id', 'runninghub_api_key'}
                        if not required <= set(value) or set(value) - required - {
                                'background_prompt', 'foreground_prompt', 'cover_prompt', 'image_config'}:
                            raise ProductError('贴片生成字段无效')
                        if not all(isinstance(value[key], str) and value[key] for key in required):
                            raise ProductError('贴片项目或 RunningHub API Key 无效')
                        return self.respond(200, sticker_result(stickers().generate_live_sticker_images(value)))
                    if path == '/api/stickers/cancel':
                        if set(value) != {'project_id'} or not isinstance(value['project_id'], str):
                            raise ProductError('贴片取消字段无效')
                        return self.respond(200, sticker_result(
                            stickers().cancel_live_sticker_generation(value['project_id'])))
                    if path == '/api/cloud-dh/create':
                        if set(value) != {'name'} or not isinstance(value['name'], str) or len(value['name']) > 100:
                            raise ProductError('云数字人项目名称无效')
                        return self.respond(201, sticker_result(stickers().create_cloud_dh_project(value['name'])))
                    if path == '/api/cloud-dh/update':
                        if (set(value) != {'project_id', 'data'} or not isinstance(value['project_id'], str)
                                or not isinstance(value['data'], dict)
                                or set(value['data']) - {'name', 'avatar_prompt'}):
                            raise ProductError('云数字人项目保存字段无效')
                        return self.respond(200, sticker_result(stickers().update_cloud_dh_project(
                            value['project_id'], value['data'])))
                    if path in ('/api/cloud-dh/import-avatar', '/api/cloud-dh/import-audio'):
                        if set(value) != {'project_id', 'source'} or not all(isinstance(item, str) and item for item in value.values()):
                            raise ProductError('云数字人素材导入字段无效')
                        kind = 'avatar' if path.endswith('avatar') else 'audio'
                        try: result = stickers()._import_cloud_dh_file(value['project_id'], kind, value['source'])
                        except Exception as error: raise ProductError(str(error)) from None
                        return self.respond(200, sticker_result(result))
                    if path == '/api/cloud-dh/generate-avatar':
                        if (not {'project_id','runninghub_api_key'} <= set(value)
                                or set(value) - {'project_id','runninghub_api_key','description'}
                                or not all(isinstance(value[key], str) and value[key] for key in ('project_id','runninghub_api_key'))):
                            raise ProductError('云数字人形象生成字段无效')
                        return self.respond(200, sticker_result(stickers().generate_cloud_dh_avatar(value)))
                    if path == '/api/cloud-dh/generate-video':
                        if set(value) != {'project_id','runninghub_api_key'} or not all(
                                isinstance(value[key], str) and value[key] for key in value):
                            raise ProductError('云数字人视频生成字段无效')
                        return self.respond(200, sticker_result(stickers().generate_cloud_dh_video(value)))
                    if path == '/api/cloud-dh/cancel':
                        if set(value) != {'project_id'} or not isinstance(value['project_id'], str):
                            raise ProductError('云数字人取消字段无效')
                        return self.respond(200, sticker_result(
                            stickers().cancel_cloud_dh_generation(value['project_id'])))
                    if path == '/api/ip-agent/create':
                        if set(value) != {'name'} or not isinstance(value['name'], str) or not 1 <= len(value['name'].strip()) <= 100:
                            raise ProductError('IP 项目名称无效')
                        return self.respond(201, ip_result(stickers().create_ip_agent_project(value['name'])))
                    if path == '/api/ip-agent/update':
                        allowed = {'name', 'publish_title', 'publish_tags', 'publish_tags_text',
                                   'publish_platforms', 'publish_accounts', 'publish_date'}
                        if (set(value) != {'project_id', 'data'} or not isinstance(value['project_id'], str)
                                or not isinstance(value['data'], dict) or set(value['data']) - allowed):
                            raise ProductError('IP 项目保存字段无效')
                        return self.respond(200, ip_result(stickers().update_ip_agent_project(
                            value['project_id'], value['data'])))
                    if path == '/api/ip-agent/delete':
                        if set(value) != {'project_id'} or not isinstance(value['project_id'], str):
                            raise ProductError('IP 项目删除字段无效')
                        return self.respond(200, ip_result(stickers().delete_ip_agent_project(value['project_id'])))
                    if path == '/api/ip-agent/import-video':
                        if (set(value) != {'project_id', 'source'}
                                or not all(isinstance(item, str) and item for item in value.values())):
                            raise ProductError('IP 成片导入字段无效')
                        return self.respond(200, ip_result(stickers().import_ip_agent_final_video(
                            value['project_id'], value['source'])))
                    if path in ('/api/ip-agent/publish-dry-run', '/api/ip-agent/publish'):
                        allowed = {'project_id', 'platforms', 'account_names', 'title', 'tags', 'publish_date',
                                   'thumbnail_path', 'request_id', 'handle_login', 'force_republish',
                                   'confirm_retry_after_interruption'}
                        if (not isinstance(value, dict) or set(value) - allowed
                                or not isinstance(value.get('project_id'), str)
                                or not isinstance(value.get('platforms'), list)):
                            raise ProductError('IP 发布字段无效')
                        payload = {key: item for key, item in value.items() if key != 'project_id'}
                        payload['dry_run'] = path.endswith('dry-run')
                        return self.respond(200, ip_result(stickers().publish_ip_agent_video(
                            value['project_id'], payload)))
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
                    if path == '/api/live/content-render':
                        required = {'session_id','task_id','avatar_id'}
                        if (not required <= set(value)
                                or not (set(value) - required) <= {'render_profile','bgm_path','bgm_volume'}):
                            raise ProductError('短视频生成字段无效')
                        if not all(isinstance(value[key], str) and value[key]
                                   for key in ('session_id', 'task_id', 'avatar_id')):
                            raise ProductError('口播记录或形象ID无效')
                        if avatar_manager is not None and (avatar_manager.state() or {}).get('status') == 'running':
                            raise Conflict('正在制作形象，请完成或取消后再合成视频')
                        return self.respond(202, {'task': renders().start_content(**value)})
                    if path == '/api/live/content-package':
                        if set(value) != {'session_id', 'task_id', 'render_task_id'} or not all(
                                isinstance(value[key], str) and 1 <= len(value[key]) <= 64 for key in value):
                            raise ProductError('需要有效的口播和成片任务编号')
                        from scripts.media_http import serve_file
                        manager = render_manager if render_manager is not None else renders()
                        package = manager.publication_package(value['session_id'], value['task_id'],
                                                              value['render_task_id'])
                        return serve_file(self, package, 'application/zip')
                    if path == '/api/render/cancel':
                        if set(value)!={'task_id'} or not isinstance(value['task_id'],str):
                            raise ProductError('视频取消字段无效')
                        manager=render_manager if render_manager is not None else renders()
                        return self.respond(200,{'task':manager.cancel(value['task_id'])})
                    if path == '/api/tts/cancel':
                        if set(value)!={'task_id'} or not isinstance(value['task_id'],str): raise ProductError('TTS取消字段无效')
                        return self.respond(200,{'task':tts().cancel(value['task_id'])})
                    if path in {"/api/live/advice/acknowledge", "/api/live/advice/revoke"}:
                        if set(value) != {'session_id', 'advice'} or not isinstance(value['session_id'], str):
                            raise ProductError('运营提醒确认字段无效')
                        session = live_manager.state() if live_manager else {'status': 'idle'}
                        if session.get('id') != value['session_id'] or value['advice'] not in current_live_advice(session):
                            raise Conflict('运营提醒已变化，请刷新后核对')
                        from time import time
                        data = products()
                        acknowledge = path.endswith('/acknowledge')
                        if acknowledge:
                            data.acknowledge_live_advice(value['session_id'], value['advice'], time())
                        else:
                            data.revoke_live_advice_acknowledgment(value['session_id'], value['advice'], time())
                        return self.respond(200, {'acknowledged': acknowledge})
                    if path == "/api/promotion/plans/action":
                        if set(value) != {'plan_id', 'action'} or not isinstance(value['plan_id'], str):
                            raise ProductError('投放方案操作字段无效')
                        return self.respond(200, {'plan': products().update_promotion_plan(**value)})
                    if path == "/api/promotion/plans":
                        if set(value) - {'expected_bill', 'expected_product_version'} != {
                                         'product_id', 'source', 'period_start', 'period_end', 'campaign', 'asset',
                                         'budget_minor', 'rationale'}:
                            raise ProductError('投放方案字段无效')
                        return self.respond(200, {'plan': products().save_promotion_plan(**value)})
                    if path == "/api/promotion/budget-preview":
                        fields = {'product_id', 'source', 'period_start', 'period_end', 'campaign', 'asset'}
                        if (set(value) != fields | {'budget_minor'} or any(
                                not isinstance(value[key], str) or not value[key].strip() for key in fields)):
                            raise ProductError('预算预览需要完整的账单定位条件')
                        budget = value['budget_minor']
                        if type(budget) is not int or not 0 <= budget < 2**53:
                            raise ProductError('预算上限须为非负整数分')
                        records = products().promotion_spend(value['product_id'])
                        bill = next((record for record in records
                                     if all(record[key] == value[key] for key in fields)), None)
                        if bill is None:
                            raise ProductError('缺少同一活动、素材及区间的账单记录')
                        remaining = budget - bill['spend_minor']
                        return self.respond(200, {'preview': {
                            'bill': bill, 'budget_minor': budget, 'remaining_minor': remaining,
                            'status': 'over_budget' if remaining < 0 else 'at_limit' if remaining == 0 else 'below_limit',
                        }})
                    if path == "/api/promotion/spend":
                        required = {'product_id', 'source', 'period_start', 'period_end', 'campaign', 'asset', 'spend_minor'}
                        if set(value) - {'attribution'} != required:
                            raise ProductError('投放费用字段无效')
                        data = products()
                        data.save_promotion_spend(**value)
                        return self.respond(200, {'records': data.promotion_spend(value['product_id'])})
                    if path == "/api/sourcing/decision":
                        if set(value) - {'expected_trial'} != {'candidate_id', 'decision', 'rationale', 'constraints'} or (
                                not isinstance(value['candidate_id'], str) or not 1 <= len(value['candidate_id']) <= 64):
                            raise ProductError('采购辅助结论字段无效')
                        return self.respond(200, {'decision': products().save_sourcing_decision(**value)})
                    if path == "/api/sourcing/trial":
                        if set(value) - {'metrics'} != {'candidate_id', 'sample_evidence', 'trial_evidence', 'cost_minor', 'verdict'} or (
                                not isinstance(value['candidate_id'], str) or not 1 <= len(value['candidate_id']) <= 64):
                            raise ProductError('样品与试卖字段无效')
                        data = products()
                        data.save_sourcing_trial(**value)
                        return self.respond(200, {'trial': data.sourcing_trial(value['candidate_id'])})
                    if path == "/api/sourcing/candidates":
                        if set(value) != {'name', 'supplier', 'source', 'observed_on', 'details'}:
                            raise ProductError('采购候选字段无效')
                        data = products()
                        candidate_id = data.save_sourcing_candidate(**value)
                        return self.respond(200, {'id': candidate_id})
                    if path == "/api/live/reply-review":
                        if set(value) != {'session_id', 'task_id', 'verdict', 'review_seconds'} or any(
                                not isinstance(value[key], str) or not 1 <= len(value[key]) <= 64
                                for key in ('session_id', 'task_id')):
                            raise ProductError('答复复核字段无效')
                        products().review_live_reply(**value)
                        return self.respond(200, {'saved': True})
                    if path == "/api/products/after-sales/task/revoke":
                        if set(value) != {'product_id', 'source', 'period_start', 'period_end', 'category'} or any(
                                not isinstance(item, str) for item in value.values()):
                            raise ProductError('售后改进任务字段无效')
                        products().revoke_after_sales_task(**value)
                        return self.respond(200, {'revoked': True})
                    if path == "/api/products/after-sales/task":
                        if set(value) - {'product_version', 'expected_count'} != {'product_id', 'source', 'period_start', 'period_end',
                                                               'category', 'owner', 'goal'}:
                            raise ProductError('售后改进任务字段无效')
                        data = products()
                        data.save_after_sales_task(**value)
                        return self.respond(200, {'tasks': data.after_sales_tasks([value['product_id']])})
                    if path == "/api/products/after-sales/import":
                        if set(value) != {'product_id', 'csv'}:
                            raise ProductError('售后导入字段无效')
                        data = products()
                        count = data.import_after_sales(value['product_id'], value['csv'])
                        return self.respond(200, {'imported': count, 'reports': data.after_sales(value['product_id'])})
                    if path == "/api/products/after-sales":
                        if set(value) != {'product_id', 'source', 'period_start', 'period_end', 'counts'}:
                            raise ProductError('售后汇总字段无效')
                        data = products()
                        data.save_after_sales(**value)
                        return self.respond(200, {'reports': data.after_sales(value['product_id'])})
                    if path == "/api/products/settlement-review":
                        fields = ('sales_minor', 'cost_minor', 'fees_minor', 'refund_loss_minor')
                        required = {'product_id', 'source', 'scope', 'period_start', 'period_end',
                                    'currency', 'basis', *fields}
                        quantities = ('fulfillment_due', 'fulfilled_on_time', 'inventory_start', 'inventory_end', 'net_units_sold')
                        if not required <= value.keys() <= required | set(quantities):
                            raise ProductError('退款复盘字段无效')
                        if value['basis'] not in ('estimate', 'settled') or value['currency'] != 'CNY':
                            raise ProductError('请选择估算或已结算，并使用人民币分录入金额')
                        if any(amount is not None and (type(amount) is not int or not 0 <= amount < 2**53)
                               for amount in (value[field] for field in fields)):
                            raise ProductError('金额须为非负整数分或未知')
                        due = value.get('fulfillment_due')
                        on_time = value.get('fulfilled_on_time')
                        if any(count is not None and (type(count) is not int or not 0 <= count < 2**53)
                               for count in (value.get(field) for field in quantities)):
                            raise ProductError('履约和库存周转数量须为非负整数或未知')
                        if due is not None and on_time is not None and on_time > due:
                            raise ProductError('准时履约数不能超过到期应履约数')
                        data = products()
                        counts = data.summarize_business_metrics(**{
                            key: value[key] for key in ('product_id', 'source', 'scope', 'period_start', 'period_end')
                        })
                        inventory_start = value.get('inventory_start')
                        inventory_end = value.get('inventory_end')
                        sold = value.get('net_units_sold')
                        turnover = None
                        if None not in (inventory_start, inventory_end, sold) and inventory_start + inventory_end > 0:
                            turnover = 2 * sold / (inventory_start + inventory_end)
                        missing = [field for field in fields if value[field] is None]
                        net = None if missing else value['sales_minor'] - sum(value[field] for field in fields[1:])
                        report_key = ('source', 'period_start', 'period_end')
                        fulfillment = next((report['counts'].get('fulfillment')
                                            for report in data.after_sales(value['product_id'])
                                            if all(report[key] == value[key].strip() for key in report_key)), None)
                        return self.respond(200, {'review': {
                            **value, 'net_minor': str(net) if net is not None and abs(net) >= 2**53 else net,
                            'orders': browser_metrics(counts)['orders'], 'refunds': browser_metrics(counts)['refunds'],
                            'fulfillment_after_sales': fulfillment,
                            'on_time_fulfillment_rate': on_time / due if due and on_time is not None else None,
                            'inventory_turnover': turnover,
                            'missing': missing, 'conclusion': 'uncertain',
                        }})
                    if path == "/api/live/content-withdraw":
                        if set(value) != {'session_id', 'task_id'} or any(
                                not isinstance(value[key], str) or not 1 <= len(value[key]) <= 64
                                for key in ('session_id', 'task_id')):
                            raise ProductError('停止复用字段无效')
                        products().withdraw_live_content_draft(**value)
                        return self.respond(200, {'withdrawn': True})
                    if path == "/api/live/content-receipt":
                        if set(value) != {'session_id', 'task_id', 'publication_id'} or any(
                                not isinstance(value[key], str) or not 1 <= len(value[key]) <= 64
                                for key in ('session_id', 'task_id')):
                            raise ProductError('发布结果字段无效')
                        data = products()
                        data.record_live_content_receipt(**value)
                        return self.respond(200, {'schedule': data.live_content_schedule(
                            value['session_id'], value['task_id'])})
                    if path == "/api/live/content-schedule":
                        if set(value) != {'session_id', 'task_id', 'account', 'audience', 'publish_at'} or any(
                                not isinstance(value[key], str) or not 1 <= len(value[key]) <= 64
                                for key in ('session_id', 'task_id')):
                            raise ProductError('排期字段无效')
                        data = products()
                        data.save_live_content_schedule(**value)
                        return self.respond(200, {'schedule': data.live_content_schedule(
                            value['session_id'], value['task_id'])})
                    if path == "/api/live/content-draft":
                        if set(value) - {'production_seconds', 'baseline_seconds'} != {'session_id', 'task_id', 'body'} or any(
                                not isinstance(value[key], str) or not 1 <= len(value[key]) <= 64
                                for key in ('session_id', 'task_id')):
                            raise ProductError('短视频草稿字段无效')
                        return self.respond(200, {'body': products().save_live_content_draft(**value)})
                    if path == "/api/live/improvements":
                        required = {'session_id', 'owner', 'goal'}
                        evidence = set(value) - required - {'adopted'}
                        if (not required <= set(value) or evidence not in ({'fault_id'}, {'reply_task_id'})
                                or not isinstance(value['session_id'], str)):
                            raise ProductError('改进任务字段无效')
                        data = products()
                        if 'reply_task_id' in value:
                            data.save_reply_improvement(**value)
                        else:
                            data.save_live_improvement(**value)
                        return self.respond(200, {'tasks': data.live_improvements(value['session_id'])})
                    if path == "/api/live/preparation/review":
                        if set(value) != {'revision', 'review'}:
                            return self.respond(400, {"error": "需要准备包版本和审阅稿"})
                        products().save_live_preparation_review(**value)
                        return self.respond(200, {"saved": True})
                    if path == "/api/live/preparation/rotation":
                        if set(value) != {'revision'}:
                            return self.respond(400, {"error": "需要准备包版本"})
                        return self.respond(200, products().live_preparation_rotation(**value))
                    if path == "/api/live/preparation/trial":
                        if set(value) != {'session_id'} or not isinstance(value['session_id'], str):
                            raise ProductError('试播场次无效')
                        data = products()
                        data.bind_live_lineup_trial(value['session_id'])
                        return self.respond(200, {'lineup_baseline': data.live_session_report(
                            value['session_id'])['lineup_baseline']})
                    if path == "/api/live/preparation/baseline":
                        if value:
                            raise ProductError('基线使用当前已保存草稿')
                        return self.respond(200, {'baseline': products().capture_live_lineup_baseline()})
                    if path == "/api/live/preparation":
                        if 'product_ids' not in value:
                            return self.respond(400, {"error": "缺少本场商品列表"})
                        data = products()
                        data.save_live_preparation(**value)
                        return self.respond(200, data.live_preparation())
                    if path == "/api/preparation-templates":
                        if set(value) != {'name', 'goal', 'audience', 'constraints'}:
                            raise ProductError('准备模板字段无效')
                        return self.respond(200, {'template': preparation_templates().save(**value)})
                    if path == "/api/preparation-templates/apply":
                        if set(value) != {'template_id'}:
                            raise ProductError('准备模板应用参数无效')
                        template = preparation_templates().get(value['template_id'])
                        data = products()
                        current = data.live_preparation()['draft']
                        data.save_live_preparation(
                            product_ids=current['product_ids'], promotion=current['promotion'],
                            stock=current['stock'], shipping=current['shipping'],
                            **{field: template[field] for field in ('goal', 'audience', 'constraints')})
                        return self.respond(200, {'template': template, **data.live_preparation()})
                    if path == "/api/products":
                        allowed = {"title", "content", "product_index", "product_id", "version", "product_facts"}
                        if not {"title", "content", "product_index"} <= value.keys() or value.keys() - allowed:
                            raise ProductError("商品字段不完整或包含未知字段")
                        return self.respond(200, {"product": products().save(**value)})
                    if path == "/api/products/business-metrics":
                        required = {"product_id", "source", "period_start", "period_end", "scope"}
                        if (not required <= value.keys()
                                or value.keys() - (required | {"clicks", "orders", "refunds", "stock"})
                                or not isinstance(value["product_id"], str)):
                            raise ProductError("经营数据字段无效")
                        data = products()
                        data.save_business_metrics(**value)
                        return self.respond(200, {"records": list(map(browser_metrics, data.business_metrics(value["product_id"])))})
                    if path == "/api/products/business-metrics/import":
                        if set(value) != {"product_id", "csv"} or not isinstance(value["product_id"], str):
                            raise ProductError("经营报表导入字段无效")
                        data = products()
                        count = data.import_business_metrics(value["product_id"], value["csv"])
                        records = list(map(browser_metrics, data.business_metrics(value["product_id"])))
                        return self.respond(200, {"imported": count, "records": records})
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
    parser.add_argument("--shop-id", help="在数据目录下使用独立的店铺工作区")
    parser.add_argument("--access-role", choices=ACCESS_ROLES,
                        default=os.environ.get('SHUZIREN_MANAGED_ACCESS_ROLE', 'admin'),
                        help="当前本机入口的访问角色")
    parser.add_argument("--account-id", default=os.environ.get('SHUZIREN_MANAGED_ACCOUNT_ID', 'local'),
                        help="写入本店权限审计的账号编号")
    parser.add_argument("--port", type=int)
    parser.add_argument("--tts-engine", choices=("indextts", "zipvoice", "omnivoice"), default="indextts")
    parser.add_argument("--tts-model-root", type=Path)
    args = parser.parse_args(argv)
    try:
        directory = shop_data_directory(args.data_directory, args.shop_id) if args.shop_id is not None else args.data_directory
    except ValueError as error:
        parser.error(str(error))
    store = ConfigStore(directory)
    store.directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=store.directory / "console.log", encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    instance = InstanceLock(store.directory)
    try:
        instance.__enter__()
        server = create_server(store, args.port, tts_engine=args.tts_engine,
                               tts_model_root=args.tts_model_root,
                               shop_id=args.shop_id or os.environ.get('SHUZIREN_MANAGED_SHOP_ID'),
                               access_role=args.access_role, access_account=args.account_id)
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
