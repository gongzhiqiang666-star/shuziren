"""Playback lifecycle for the recovered face/hand live mode."""

from dataclasses import dataclass
from threading import Event, Lock, Thread, current_thread
from queue import Empty, Queue
from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep, time
import traceback

from .local_voice import synthesize_local_audio
from .face_hand_player import FaceHandVideoStreamManager
from .face_hand_video_group import load_face_hand_video_group
from .output_resolution import resolve_portrait_size
from .text_processing import process_script_options, process_special_variables, strip_prohibited_words

TTS_EMIT_BURST_MAX=4
TTS_PIPELINE_DEPTH=4
BROADCAST_QUEUE_TARGET=800
PRODUCT_SWITCH_QUEUE_THRESHOLD=0
INTERACTION_OFF_SECONDS=100000
INTERACTION_MESSAGE_CAP=500
TTS_CLOUD_TIMEOUT_SECONDS=90.0
TTS_LOCAL_TIMEOUT_SECONDS=120.0
AUDIO_PRODUCT_MAP_LIMIT=1000


@dataclass
class InteractionMessage:
    msg_type: str
    nickname: str
    content: str
    timestamp: float
    processed: bool = False


def _is_entrance_message_content(content):
    lowered = str(content or "").strip().lower()
    return any(marker in lowered for marker in ("进入直播间", "进入了直播间", "joined live", "joined the live"))


def _normalize_interaction_msg_type(msg_type, content=""):
    value = str(msg_type or "弹幕").strip()
    if value in {"分享","comment","chat"}:
        value="弹幕"
    elif value in {"enter","进入","进直播间","member","join","进入直播间"}:
        value="进入直播间"
    elif value in {"follow","关注主播"}:
        value="关注"
    elif value in {"gift","礼物","点赞","like"}:
        value="礼物"
    if value == "弹幕" and _is_entrance_message_content(content):
        return "进入直播间"
    return value or "弹幕"


class FaceHandLiveManager:
    def __init__(self, main_config):
        self._main_config = main_config
        self._live_config = {}
        self._player = None
        self._last_error = None
        self._product_script_groups = []
        self.product_script_groups = self._product_script_groups
        self._group_index = 0; self.current_product_index=-1; self._pending_group=-1
        self.phase="idle"; self.product_item_cursor=0
        self.product_info=str(self._main_config.get("product_info") or "")
        self._stop = Event(); self._audio_stop = Event(); self._audio_worker = None; self._session_thread = None
        self._session_stop=Event(); self._tick_lock=Lock(); self._started_cycle=False
        self._audio_task_queues = {"danmu":Queue(), "manual":Queue(), "normal":Queue()}
        self._pending_audio = {key:0 for key in self._audio_task_queues}; self._pending_lock=Lock(); self._lock=Lock()
        self._manual_speaks=[]; self._simulated_questions=[]; self.interaction_messages=[]
        self.llm_config={}
        self.minimax_voice_config={}
        self.cosyvoice_voice_config={}
        self.blocked_users=[]; self.welcomed_nicknames=set()
        self.comment_reply_interval=0; self.entrance_reply_interval=0
        self.follow_reply_interval=0; self.gift_reply_interval=0
        self.last_comment_reply=0.0; self.last_entrance_reply=0.0
        self.last_follow_reply=0.0; self.last_gift_reply=0.0
        self._danmu_capturer=None; self._danmu_thread=None; self._voice_synthesizer=None; self._voice_key=None
        self._voice_synthesizers={}
        self._audio_product_map={}
        self._normal_audio_epoch=0
        self.host_streamer=None
        self._primary_voice_id=""
        self.voice_infer_version="v1"
        self.voice_speed=1.1
        self.language="zh-CN"
        self.use_audio_cache=True
        self._interaction_llm_executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix="face-hand-interaction")
        self.qa_info=""; self.special_instructions=""; self.reply_blocked_keywords=[]
        self.question_blocked_keywords=[]
        self._taobao_controller=None; self._product_popup=None
        self.product_image_items=[]
        self.product_image_jitter_level=5
        self._synced_goods_id=None
        self._synced_image_goods_id=None
        self._last_synced_product=None

    @property
    def last_error(self):
        return self._last_error or (self._player.last_error if self._player else None)

    @property
    def is_broadcasting(self):
        return self._player is not None and self._player.is_playing

    @staticmethod
    def _build_product_groups(products):
        from .slice_content import slice_content
        groups = []
        for product_index, product in enumerate(products or []):
            if not isinstance(product, dict):
                continue
            scripts=str(product.get("scripts") or "").strip()
            if not scripts:continue
            try:index=int(product.get("product_index",product_index))
            except Exception:index=product_index
            items=[]
            for item in slice_content(scripts):
                item=dict(item);item["product_index"]=index;items.append(item)
            if items:
                groups.append({"product_index":index,
                               "product_info":str(product.get("content") or product.get("itemName") or ""),
                               "items":items})
        return groups

    def start_live(self, *, config, llm_config=None, minimax_voice_config=None, cosyvoice_voice_config=None):
        if self.is_broadcasting:
            return False
        self._last_error = None
        try:
            products = config.get("products") or config.get("product_scripts") or []
            product_groups = self._build_product_groups(products)
            group = load_face_hand_video_group(config["face_hand_video_group_dir"])
            width, height = resolve_portrait_size(config.get("resolution"))
            player = FaceHandVideoStreamManager(
                face_videos=group["face"], hand_videos=group["hand"],
                window_width=width, window_height=height,
                image_output_mode=config.get("output_mode") or "window",
            )
            self._live_config = dict(
                config,
                llm_config=llm_config or config.get("llm_config") or {},
                cosyvoice_voice_config=cosyvoice_voice_config or config.get("cosyvoice_voice_config"),
                minimax_voice_config=minimax_voice_config or config.get("minimax_voice_config"),
            )
            self.qa_info=self._live_config.get("qa_info") or ""
            self.llm_config=dict(self._live_config.get("llm_config") or {})
            self.minimax_voice_config=dict(self._live_config.get("minimax_voice_config") or {})
            self.cosyvoice_voice_config=dict(self._live_config.get("cosyvoice_voice_config") or {})
            self.special_instructions=str(self._live_config.get("special_instructions") or "")
            self.reply_blocked_keywords=list(self._live_config.get("reply_blocked_keywords") or [])
            self.question_blocked_keywords=list(self._live_config.get("question_blocked_keywords") or [])
            self._primary_voice_id=str(self._live_config.get("voice_id") or "").strip()
            self.voice_infer_version=str(self._live_config.get("voice_infer_version") or "v1")
            self.voice_speed=float(self._live_config.get("voice_speed") or 1.1)
            self.language=str(self._live_config.get("language") or "zh-CN")
            self.use_audio_cache=bool(self._live_config.get("use_audio_cache",True))
            self.blocked_users=list(self._live_config.get("blocked_users") or [])
            self.comment_reply_interval=int(self._live_config.get("comment_reply_interval") or 0)
            self.entrance_reply_interval=int(self._live_config.get("entrance_reply_interval") or 0)
            self.follow_reply_interval=int(self._live_config.get("follow_reply_interval") or 0)
            self.gift_reply_interval=int(self._live_config.get("gift_reply_interval") or 0)
            self._product_script_groups = product_groups
            self.product_script_groups = product_groups
            self.product_info=str(self._live_config.get("product_info") or "")
            self._player = player
            self.host_streamer = player
            player.set_on_face_done(self._on_face_done)
            if not self._enter_face_phase(0) or not player.start_playing():
                self._last_error = player.last_error or "无法启动人脸片段"
                self.stop_live()
                return False
            self._started_cycle=True
            self._stop.clear(); self._session_stop.clear(); self._start_audio_worker(); self._prepare_product_images(); self._prepare_taobao_control()
            self._session_thread=Thread(target=self._session_loop,name="face-hand-session",daemon=True); self._session_thread.start()
            if config.get("enable_danmu_capture"): self.start_danmu()
            return True
        except Exception as error:
            self._last_error = str(error)
            self.stop_live()
            return False

    def stop_live(self):
        self._stop.set(); self._session_stop.set(); self.stop_danmu(); self._stop_audio_worker()
        thread,self._session_thread=self._session_thread,None
        if thread and thread is not current_thread(): thread.join(timeout=2)
        if self._player is not None:
            self._player.stop_playing()
            self._player = None
        self.host_streamer = None
        self._product_script_groups = []
        self.product_script_groups = self._product_script_groups
        for synthesizer in self._voice_synthesizers.values():
            try: synthesizer.clear()
            except Exception: pass
        self._voice_synthesizers.clear(); self._voice_synthesizer=None; self._voice_key=None
        if self._product_popup:
            try:
                from .product_image_popup import close_product_image_popup
                close_product_image_popup()
            except Exception: pass
            self._product_popup=None
        if self._live_config.get("enable_product_image_cutout"):
            try:
                from .product_cutout import unload_product_cutout
                unload_product_cutout()
            except Exception: pass
        self.product_image_items=[]; self._synced_goods_id=None; self._synced_image_goods_id=None
        self._started_cycle=False
        return True

    def _enter_face_phase(self, group_index):
        if not self.product_script_groups:
            return False
        group_index=int(group_index)%len(self.product_script_groups)
        self._clear_normal_queues()
        if not self._player.play_face_clip():
            return False
        self.phase="face"; self._pending_group=group_index
        self.current_product_index=-1; self.product_item_cursor=0
        return True

    def _on_face_done(self):
        if self.phase != "face" or not self.product_script_groups:
            return
        group_index=self._pending_group%len(self.product_script_groups)
        self.phase="hand"; self.current_product_index=group_index
        self._group_index=group_index; self.product_item_cursor=0
        self._player.play_hand_clip()

    def _queue_scripts(self, player, config, scripts):
        for item in scripts:
            if self._player is not player or not player.is_playing:
                return
            try:
                self._emit_script_item_for(item, player, config)
            except Exception as error:
                if self._player is player:
                    self._last_error = str(error)

    def _active_product_info(self):
        groups=self.product_script_groups
        for index in (self.current_product_index,self._pending_group):
            if 0 <= index < len(groups):
                value=groups[index].get("product_info")
                if value:
                    value=str(value).strip()
                    if value:return value
        return self.product_info

    @staticmethod
    def _format_product_info(product):
        return str(product.get("product_info") or "").strip()

    def _emit_script_item(self, item):
        if item["type"] != "host":
            return None
        text=process_special_variables(item.get("content"))
        text=process_script_options(text).strip()
        if text:
            self._enqueue_tts(text,queue="normal",product_index=item.get("product_index"))
        return None

    def _emit_script_item_for(self, item, player, config):
        if isinstance(item, dict):
            audio_path = item.get("audio_path")
        else:
            item = process_special_variables(item)
            item = strip_prohibited_words(item, config.get("prohibited_words") or ())
            if not item.strip():
                return
            voice_ids = config.get("voice_ids") or []
            voice_id = next(
                (voice.strip() for voice in voice_ids if isinstance(voice, str) and voice.strip()),
                (config.get("voice_id") or "").strip(),
            )
            provider = ((config.get("voice_general_config") or {}).get("provider") or "").strip().lower()
            if provider == "cosyvoice":
                from .cosyvoice import synthesize_speech_cosyvoice

                voice_config = config.get("voice_general_config") or {}
                audio_path = synthesize_speech_cosyvoice(
                    text=item,
                    voice_id=voice_config.get("cosyvoice_voice_id") or voice_id,
                    cosyvoice_config=config.get("cosyvoice_voice_config") or {},
                    speed=float(config.get("voice_speed") or 1.1),
                )
            elif provider == "minimax":
                from .minimax import synthesize_speech_minimax

                audio_path = synthesize_speech_minimax(
                    text=item,
                    voice_id=(config.get("voice_general_config") or {}).get("minimax_voice_id") or voice_id,
                    minimax_config=config.get("minimax_voice_config") or {},
                    speed=float(config.get("voice_speed") or 1.1),
                )
            else:
                audio_path = synthesize_local_audio(
                    self._main_config, voice_id, item, float(config.get("voice_speed") or 1.1),
                    config.get("voice_infer_version") or "v1",
                )
        if audio_path and self._player is player and player.is_playing:
            player.add_audio_to_queue(audio_path)

    @staticmethod
    def _build_product_image_items(products):
        result=[]
        for item in products or []:
            if not isinstance(item,dict):
                continue
            item_pic=str(item.get("itemPic") or item.get("item_pic") or "").strip()
            if item_pic.startswith("//"):
                item_pic="https:"+item_pic
            result.append({
                "itemPic":item_pic,
                "itemName":str(item.get("itemName") or item.get("item_name") or "").strip(),
                "itemId":str(item.get("itemId") or item.get("item_id") or "").strip(),
            })
        return result

    def _pending_audio_snapshot(self):
        with self._pending_lock: return dict(self._pending_audio)
    def _adjust_pending_audio(self,queue_name,delta):
        with self._pending_lock: self._pending_audio[queue_name]=max(0,self._pending_audio.get(queue_name,0)+delta)
    def _enqueue_audio_task(self,task,queue_name):
        queue_name=queue_name if queue_name in self._audio_task_queues else "normal"
        self._adjust_pending_audio(queue_name,1); self._audio_task_queues[queue_name].put(task)
    def _take_next_audio_task(self):
        for name in ("manual","danmu","normal"):
            try: return self._audio_task_queues[name].get_nowait(),name
            except Empty: pass
        return None,None
    def _audio_worker_loop(self):
        while not self._audio_stop.is_set():
            task,name=self._take_next_audio_task()
            if task is None: self._audio_stop.wait(.05); continue
            try:
                if task.get("type")=="tts_speak": self._handle_tts_speak(task.get("payload") or {})
                elif task.get("type")=="audio" and self._player: self._player.add_audio_to_queue(task.get("path"),queue_name=name)
            except Exception as error:
                print(f"[face_hand.live] 音频任务异常: {error}")
                traceback.print_exc()
            finally: self._adjust_pending_audio(name,-1)
    def _start_audio_worker(self):
        if self._audio_worker and self._audio_worker.is_alive(): return
        self._audio_stop.clear(); self._audio_worker=Thread(target=self._audio_worker_loop,daemon=True); self._audio_worker.start()
    def _stop_audio_worker(self):
        self._audio_stop.set(); thread,self._audio_worker=self._audio_worker,None
        if thread and thread is not current_thread(): thread.join(2)
    def _clear_normal_queues(self):
        self._normal_audio_epoch+=1
        queue=self._audio_task_queues["normal"]
        while True:
            try: queue.get_nowait(); self._adjust_pending_audio("normal",-1)
            except Empty: break
        if self._player: self._player.clear_audio_queues()

    def _enqueue_tts(self,text,*,queue="normal",product_index=None):
        text=str(text or "").strip()
        if text: self._enqueue_audio_task({"type":"tts_speak","payload":{"text":text,"queue":queue,"product_index":product_index,"epoch":self._normal_audio_epoch}},queue)
    def _handle_tts_speak(self,payload):
        text=process_special_variables(payload.get("text","")); text=strip_prohibited_words(text,self._live_config.get("prohibited_words") or ())
        if not text or not self._player: return
        queue_name=str(payload.get("queue") or "normal")
        epoch=int(payload.get("epoch") or 0)
        product_index=payload.get("product_index")
        voice_id=str(payload.get("voice_id") or self._primary_voice_id).strip()
        voice_infer_version=str(payload.get("voice_infer_version") or self.voice_infer_version)
        voice_speed=float(payload.get("voice_speed") or self.voice_speed)
        language=str(payload.get("language") or self.language)
        use_audio_cache=bool(payload.get("use_audio_cache",self.use_audio_cache))
        voice_general_config=payload.get("voice_general_config") or {}
        if voice_infer_version == "minimax":
            from .minimax import synthesize_speech_minimax
            runtime_config=self._build_minimax_runtime_config(voice_general_config)
            audio=self._run_with_timeout(
                lambda:synthesize_speech_minimax(
                    text=text,voice_id=runtime_config.get("minimax_voice_id") or voice_id,
                    minimax_config=runtime_config,speed=voice_speed,language=language,
                    use_cache=use_audio_cache),
                TTS_CLOUD_TIMEOUT_SECONDS,"迷你马克斯语音合成")
        elif voice_infer_version == "cosyvoice":
            from .cosyvoice import synthesize_speech_cosyvoice
            runtime_config=self._build_cosyvoice_runtime_config(voice_general_config)
            audio=self._run_with_timeout(
                lambda:synthesize_speech_cosyvoice(
                    text=text,voice_id=runtime_config.get("cosyvoice_voice_id") or voice_id,
                    cosyvoice_config=runtime_config,speed=voice_speed,language=language,
                    use_cache=use_audio_cache),
                TTS_CLOUD_TIMEOUT_SECONDS,"阿里云语音合成")
        else:
            synth=self._ensure_voice_synthesizer(voice_id,voice_infer_version)
            audio=self._run_local_synth_with_timeout(
                lambda:synth.synthesize(text=text,speed=voice_speed,language=language,use_cache=use_audio_cache),
                TTS_LOCAL_TIMEOUT_SECONDS,"本地语音合成")
        streamer=self.host_streamer or self._player
        if not audio or not self.is_broadcasting or not streamer:
            return
        if queue_name == "normal" and epoch != self._normal_audio_epoch:
            print("[face_hand.live] 忽略过期的普通音频任务")
            return
        streamer.add_audio_to_queue(audio,queue_name=queue_name)
        if product_index is not None and queue_name == "normal":
            try:
                self._audio_product_map[str(audio)] = int(product_index)
            except (TypeError,ValueError):
                pass
            overflow=len(self._audio_product_map)-AUDIO_PRODUCT_MAP_LIMIT
            if overflow > 0:
                for key in list(self._audio_product_map)[:overflow]:
                    self._audio_product_map.pop(key,None)

    def _ensure_voice_synthesizer(self,voice_id,voice_infer_version):
        key=(voice_id,voice_infer_version)
        if key not in self._voice_synthesizers:
            from importlib import import_module
            from .local_voice import MODULES
            cls=import_module(MODULES[voice_infer_version]).VoiceSynthesizer
            self._voice_synthesizers[key]=cls.from_voice_dir(self._main_config.get("models_base_path","assets/pretrained_models"),self._main_config["voice_base_dir"],voice_id,self._main_config.get("device","cuda"),voice_infer_version)
        self._voice_synthesizer=self._voice_synthesizers[key]; self._voice_key=key
        return self._voice_synthesizer

    def _run_with_timeout(self,func,timeout,description):
        result=[]; error=[]
        def runner():
            try: result.append(func())
            except BaseException as exc: error.append(exc)
        thread=Thread(target=runner,daemon=True); thread.start(); thread.join(float(timeout))
        if thread.is_alive(): raise TimeoutError(f"{description}超时")
        if error: raise error[0]
        return result[0] if result else None
    _run_local_synth_with_timeout=_run_with_timeout

    @staticmethod
    def _interaction_enabled(interval):
        return int(interval) < INTERACTION_OFF_SECONDS
    def _normalize_control_text_reply(self,reply,nickname):
        from .taobao_live_control import COMMENT_MAX_LEN
        text=str(reply or "").strip();name=str(nickname or "").strip() or "用户";mention=f"@{name}"
        if text.startswith(mention): normalized=text
        elif not text.startswith("@"): normalized=f"{mention} {text}"
        else:
            parts=text.split(" ",1);normalized=mention+(f" {parts[1]}" if len(parts)>1 else "")
        normalized=" ".join(normalized.split())
        return normalized[:int(COMMENT_MAX_LEN)].strip()
    def request_manual_speak(self,text):
        text=str(text or "").strip()
        if not text or not self.is_broadcasting: return False
        with self._lock:self._manual_speaks.append(text)
        return True
    def request_simulated_question(self,content):
        content=str(content or "").strip()
        if not content or not self.is_broadcasting: return False
        with self._lock:self._simulated_questions.append(content)
        return True
    def submit_danmu(self,message):
        if not isinstance(message,dict):
            return None
        nickname=str(message.get("nickname") or message.get("user") or "").strip()
        content=str(message.get("content") or message.get("text") or "").strip()
        if not nickname:
            return None
        msg_type=_normalize_interaction_msg_type(
            message.get("msg_type") or message.get("type") or "弹幕",content)
        raw_timestamp=message.get("timestamp")
        try:timestamp=float(raw_timestamp or time())
        except (TypeError,ValueError):timestamp=time()
        interaction=InteractionMessage(msg_type,nickname,content,timestamp)
        with self._lock:
            if msg_type == "进入直播间":
                self.interaction_messages.insert(0,interaction)
            else:
                self.interaction_messages.append(interaction)
            del self.interaction_messages[:-INTERACTION_MESSAGE_CAP]
        return None
    def _drain_manual_and_simulated(self):
        with self._lock:
            manuals=list(self._manual_speaks); self._manual_speaks.clear()
            questions=list(self._simulated_questions); self._simulated_questions.clear()
        for text in manuals:self._enqueue_tts(text,queue="danmu")
        for content in questions:
            self.submit_danmu({"msg_type":"弹幕","nickname":"模拟用户","content":content})
    def _tick_broadcast(self):
        if self.phase != "hand" or self.current_product_index < 0 or not self.product_script_groups:
            return
        for _ in range(TTS_EMIT_BURST_MAX):
            lengths=self.get_queue_lengths()
            normal=int(lengths.get("normal") or 0)
            pending=int(lengths.get("pending_normal") or 0)
            if pending >= TTS_PIPELINE_DEPTH or normal >= BROADCAST_QUEUE_TARGET:
                return
            group=self.product_script_groups[self.current_product_index%len(self.product_script_groups)]
            items=group.get("items") or []
            if self.product_item_cursor >= len(items):
                if normal <= PRODUCT_SWITCH_QUEUE_THRESHOLD and pending <= 0:
                    next_group=(self.current_product_index+1)%len(self.product_script_groups)
                    print(f"[face_hand.live.dbg] 话术耗尽触发过品 from_product={self.current_product_index} to_product={next_group}",flush=True)
                    self._enter_face_phase(next_group)
                return
            item=items[self.product_item_cursor]
            self.product_item_cursor+=1
            self._emit_script_item(item)
    def _tick_interactions(self):
        if not self.llm_config:
            return
        from .llm_reply import reply_danmu, reply_enter, reply_follow, reply_like
        from .text_processing import contains_blocked
        now=time()
        with self._lock:
            messages=[item for item in self.interaction_messages if not item.processed][:20]
        for message in messages:
            message.processed=True
            nickname=message.nickname or "观众"; content=message.content or ""
            kind=str(message.msg_type or "comment").lower()
            if nickname in self.blocked_users or contains_blocked(content,self.reply_blocked_keywords):
                continue
            product_info=self._active_product_info()
            if kind == "礼物":
                interval=self.gift_reply_interval
                if (not self._interaction_enabled(interval) or
                        now-self.last_gift_reply < interval):
                    continue
                self.last_gift_reply=now
                self._submit_interaction_llm(
                    kind="gift",
                    llm_call=lambda name=nickname,product=product_info:
                        reply_like(name,product,self.special_instructions))
            elif kind == "弹幕":
                interval=self.comment_reply_interval
                if (not self._interaction_enabled(interval) or
                        contains_blocked(content,self.question_blocked_keywords) or
                        now-self.last_comment_reply < interval):
                    continue
                self.last_comment_reply=now
                if self._live_config.get("enable_ai_control_reply"):
                    self._submit_ai_control_reply(nickname,content,product_info)
                self._submit_interaction_llm(
                    kind="comment",
                    llm_call=lambda name=nickname,text=content,product=product_info:
                        reply_danmu(name,text,product,self.qa_info,self.special_instructions))
            elif kind == "关注":
                interval=self.follow_reply_interval
                if (not self._interaction_enabled(interval) or
                        now-self.last_follow_reply < interval):
                    continue
                self.last_follow_reply=now
                self._submit_interaction_llm(
                    kind="follow",
                    llm_call=lambda name=nickname,product=product_info:
                        reply_follow(name,product,self.special_instructions))
            elif kind == "进入直播间":
                interval=self.entrance_reply_interval
                if (nickname in self.welcomed_nicknames or
                        not self._interaction_enabled(interval) or
                        now-self.last_entrance_reply < interval):
                    continue
                self.welcomed_nicknames.add(nickname)
                self.last_entrance_reply=now
                self._submit_interaction_llm(
                    kind="entrance",
                    llm_call=lambda name=nickname,product=product_info:
                        reply_enter(name,product,self.special_instructions))
    def _tick(self):
        if not self._tick_lock.acquire(blocking=False):
            return
        try:
            if not self._started_cycle:
                self._started_cycle=True
                self._enter_face_phase(0)
                return
            self._drain_manual_and_simulated()
            self._tick_interactions()
            self._tick_broadcast()
        finally:
            self._tick_lock.release()
    def _session_loop(self):
        while not self._session_stop.is_set() and self.is_broadcasting:
            try:
                streamer=self.host_streamer
                if (self.phase == "face" and streamer and
                        streamer.consume_face_clip_done()):
                    self._on_face_done()
                self._tick()
                self._sync_playing_product()
            except Exception as error:
                print(f"[face_hand.live] tick 异常: {error}")
            if self._session_stop.wait(.05):
                return

    def _submit_interaction_llm(self,*,kind,llm_call):
        def runner():
            try:
                reply = llm_call()
                if not reply:
                    return
                text = str(reply).strip()
                if text:
                    self._enqueue_tts(text, queue="danmu")
            except Exception as error:
                print(f"[face_hand.live] 互动LLM失败 kind={kind}: {error}")
        executor = self._interaction_llm_executor
        if executor is None:
            runner()
        else:
            executor.submit(runner)
        return None
    def _submit_ai_control_reply(self,nickname,content,product_info):
        executor=self._interaction_llm_executor
        qa_info=self.qa_info
        special=self.special_instructions

        def worker():
            from .llm_reply import generate_text_reply
            try:
                reply=generate_text_reply(nickname,content,product_info,qa_info,special)
                if not reply:
                    reply=f"@{nickname} 收到，稍等主播回复哦"
                reply=self._normalize_control_text_reply(reply,nickname)
                if self.is_broadcasting:
                    print(f"[face_hand.live] 场控回复：{reply[:80]}")
                    self._send_taobao_control_reply(reply)
            except Exception as error:
                print(f"[face_hand.live] AI场控 LLM 异常: {error}")

        if executor is None:
            worker()
        else:
            executor.submit(worker)
        return None

    def start_danmu(self):
        if self._danmu_capturer: return False
        try:
            platform=self._live_config.get("live_platform","douyin"); url=self._live_config.get("live_url")
            if platform=="taobao" and self._taobao_controller:
                from .taobao_control_capture import TaobaoControlDanmuCapture
                capture=TaobaoControlDanmuCapture._configured(controller=self._taobao_controller)
            else:
                from .ws_capture import BarrageCapture
                capture=BarrageCapture(platform,url)
            capture.start(); self._danmu_capturer=capture; self._danmu_thread=Thread(target=self._danmu_loop,daemon=True); self._danmu_thread.start(); return True
        except Exception as error: self._last_error=str(error); return False
    def _danmu_loop(self):
        capture=self._danmu_capturer
        try:
            for message in capture:
                if capture is not self._danmu_capturer: return
                self.submit_danmu(message)
        except Exception as error:
            if capture is self._danmu_capturer: self._last_error=str(error)
    def stop_danmu(self):
        capture,self._danmu_capturer=self._danmu_capturer,None
        if capture:
            try: capture.stop()
            except Exception as error: self._last_error=str(error)
        thread,self._danmu_thread=self._danmu_thread,None
        if thread and thread is not current_thread(): thread.join(2)

    def _build_minimax_runtime_config(self,voice_general_config):
        selected = (voice_general_config or {}).get("minimax") or {}
        runtime = dict(self.minimax_voice_config)
        selected_voice_id = str(selected.get("minimax_voice_id") or "").strip()
        if selected_voice_id:
            runtime["minimax_voice_id"] = selected_voice_id
        return runtime

    def _build_cosyvoice_runtime_config(self,voice_general_config):
        from .online_voice_generate import resolve_aliyun_voice_runtime
        selected = (voice_general_config or {}).get("cosyvoice") or {}
        runtime = resolve_aliyun_voice_runtime(self.cosyvoice_voice_config)
        selected_voice_id = str(selected.get("cosyvoice_voice_id") or "").strip()
        if selected_voice_id:
            runtime["cosyvoice_voice_id"] = selected_voice_id
        return runtime
    def _prepare_product_images(self):
        if not self._live_config.get("enable_product_image_sync"):
            self.product_image_items=[]
            return
        from .product_image_popup import clamp_product_image_jitter_level,get_product_image_popup
        enable_cutout=bool(self._live_config.get("enable_product_image_cutout"))
        if enable_cutout:
            from .product_cutout import load_product_cutout
            load_product_cutout()
        self.product_image_items=self._build_product_image_items(
            self._live_config.get("products") or self._live_config.get("product_scripts") or [])
        self.product_image_jitter_level=clamp_product_image_jitter_level(
            self._live_config.get("product_image_jitter_level",5))
        self._product_popup=get_product_image_popup()
        self._product_popup.preload_products(
            self.product_image_items,enable_cutout=enable_cutout,
            enable_jitter=bool(self._live_config.get("enable_product_image_jitter")),
            jitter_level=self.product_image_jitter_level)
    def _sync_product_image(self,product_index):
        if not self._live_config.get("enable_product_image_sync"):
            return
        if not (0<=product_index<len(self.product_image_items)):
            return
        from .product_image_popup import get_product_image_popup
        popup=self._product_popup or get_product_image_popup()
        self._product_popup=popup
        item=self.product_image_items[product_index]
        try: goods_id=int(item.get("itemId") or product_index)
        except (TypeError,ValueError): goods_id=product_index
        if goods_id == self._synced_image_goods_id:
            return
        popup.show_product(goods_id=goods_id,item_pic=item.get("itemPic") or "",
                           item_name=item.get("itemName") or item.get("item_name") or "")
        self._synced_image_goods_id=goods_id
    def _prepare_taobao_control(self):
        if not self._live_config.get("enable_taobao_product_sync",self._live_config.get("enableTaobaoProductSync",False)): return
        from .taobao_live_control import TaobaoLiveControl
        self._taobao_controller=TaobaoLiveControl(); self._taobao_controller._connect_configured(storage_state=self._live_config.get("taobao_storage_state"))
    def _send_taobao_control_reply(self,reply):
        from .taobao_live_control import get_taobao_controller
        from .text_processing import contains_blocked
        text=str(reply or "").strip()
        if not text or contains_blocked(text,self.reply_blocked_keywords):
            return False
        try:
            controller=get_taobao_controller()
            if not controller.connected():
                print("[face_hand.live] AI场控发送跳过：中控台未连接")
                return False
            result=controller.send_comment(text)
            print(f"[face_hand.live] AI场控已发送: {text[:50]}")
            return bool(result)
        except Exception as error:
            print(f"[face_hand.live] AI场控发送失败: {error}")
            return False
    def _sync_product_ui(self,product_index):
        product_index=max(int(product_index),0)
        if (self._live_config.get("enable_taobao_product_sync") and
                self._synced_goods_id != product_index):
            try:
                from .taobao_live_control import get_taobao_controller
                controller=get_taobao_controller()
                if not controller.connected():
                    print(f"[face_hand.live] 中控未连接，跳过弹窗商品{product_index}")
                else:
                    controller.set_active_goods(product_index)
                    print(f"[face_hand.live] 中控弹窗商品{product_index}")
                self._synced_goods_id=product_index
            except Exception as error:
                print(f"[face_hand.live] 中控弹窗失败: {error}")
        self._sync_product_image(product_index)
    def _sync_playing_product(self):
        if self.phase != "hand":
            return
        if not (self._live_config.get("enable_taobao_product_sync") or
                self._live_config.get("enable_product_image_sync")):
            return
        if not self.host_streamer:
            return
        try:
            audio_path=self.host_streamer.get_current_playing_audio_path()
        except Exception:
            return
        if not audio_path or str(audio_path).startswith("<"):
            return
        product_index=self._audio_product_map.get(str(audio_path))
        if product_index is not None:
            self._sync_product_ui(int(product_index))
    def _pause_product_ui(self):
        if self._live_config.get("enable_taobao_product_sync"):
            try:
                from .taobao_live_control import get_taobao_controller
                get_taobao_controller().clear_active_goods()
            except Exception as error:
                print(f"[face_hand.live] 过品停中控弹窗失败: {error}")
            self._synced_goods_id=None
        if self._live_config.get("enable_product_image_sync"):
            try:
                from .product_image_popup import get_product_image_popup
                get_product_image_popup().show_greenscreen()
            except Exception as error:
                print(f"[face_hand.live] 过品绿幕失败: {error}")
            self._synced_image_goods_id=None
    def get_queue_lengths(self):
        lengths=self._player.get_queue_lengths() if self._player else {}
        pending=self._pending_audio_snapshot()
        return {key:int(lengths.get(key,0))+int(pending.get(key,0)) for key in set(lengths)|set(pending)}
