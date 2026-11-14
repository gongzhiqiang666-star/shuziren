"""Lifecycle adapter for the packaged digital-human image runtime."""

from itertools import cycle
from pathlib import Path
from queue import Queue
from threading import Event, Lock, RLock, Thread, current_thread
from time import monotonic

from .danmu_bridge import DanmuBridge, KuaishouDanmuBridge, OCRDanmuBridge, PinduoduoDanmuBridge
from .cosyvoice import synthesize_speech_cosyvoice
from .minimax import synthesize_speech_minimax
from .digital_image_runtime import create_image_runtime
from .llm_reply import generate_text_reply
from .local_voice import synthesize_local_audio
from .text_processing import contains_blocked, is_user_blocked, match_keywords, parse_qa_info, parse_qa_info_from_text, strip_prohibited_words


_NON_OCR_PLATFORMS = {"douyin", "kuaishou", "meituan", "shipinhao", "tiktok", "pinduoduo", "taobao", "shopee"}
_BRIDGE_EVENT_TYPES = {1: "danmu", 2: "like", 3: "enter", 4: "follow", 5: "gift", 8: "share"}

class DigitalLiveManager:
    def __init__(self, config, runtime_dir):
        self.config = config
        self.runtime_dir = runtime_dir
        self._runtime = None
        self._danmu_capture = None
        self._danmu_worker = None
        self._danmu_on_message = None
        self._danmu_lock = RLock()
        self._manual_lock = Lock()
        self._manual_queue = None
        self._last_interaction = {}
        self._welcomed_nicknames = set()
        self._script_stop = Event()
        self._script_worker = None
        self.current_session_id = None
        self.last_error = None

    @property
    def is_broadcasting(self):
        return self._runtime is not None

    @property
    def is_capturing(self):
        return self._danmu_capture is not None

    def start_live(
        self, *, local_params, config, llm_config=None,
        minimax_voice_config=None, cosyvoice_voice_config=None,
    ):
        if self.is_broadcasting:
            return False
        self.last_error = None
        runtime = None
        try:
            params = dict(
                local_params,
                interaction_config=config.copy(),
                llm_config=dict(llm_config or self.config.get("llm_config") or {}),
                product_info=config.get("product_info") or "",
                qa_info=config.get("qa_info") or "",
                voice_general_config=dict(config.get("voice_general_config") or {}),
                minimax_voice_config=dict(minimax_voice_config or {}),
                cosyvoice_voice_config=dict(cosyvoice_voice_config or {}),
            )
            audio_files = []
            if local_params.get("script_input_mode") == "audio":
                audio_files = self._load_script_audio_files(local_params.get("script_audio_dir"))
            scripts = []
            if local_params.get("script_input_mode", "text") == "text":
                scripts = self._load_text_script_items(config)
            self._prepare_kt_overlay(config, local_params)
            runtime = create_image_runtime(self.config, self.runtime_dir, local_params)
            if runtime.start_playing() is False:
                raise RuntimeError(getattr(runtime, "last_error", None) or "本地智播启动失败")
            if audio_files:
                runtime.add_audio_to_queue(audio_files[0])
            if audio_files or scripts:
                self._script_stop.clear()
                self._script_worker = Thread(
                    target=self._feed_script_audio, args=(runtime, audio_files or scripts, None if audio_files else params),
                    daemon=True,
                )
                self._script_worker.start()
        except Exception as error:
            self.last_error = str(error)
            if runtime is not None:
                try:
                    runtime.stop_playing()
                except Exception as cleanup_error:
                    self._runtime = runtime
                    self.last_error = f"{error}（清理失败：{cleanup_error}）"
            if self._runtime is None:
                self._close_kt_overlay()
            return False
        self._script_stop.clear()
        self._last_interaction.clear()
        self._welcomed_nicknames.clear()
        self._local_params = params
        self._script_audio_files = audio_files
        self._runtime = runtime
        self.current_session_id = getattr(runtime, "current_session_id", None)
        if config.get("enable_danmu_capture", config.get("enableDanmuCapture", False)):
            platform = (config.get("live_platform") or "douyin").strip().lower()
            live_url = (config.get("live_url") or "").strip()
            if not self.start_danmu(live_url, platform):
                error = self.last_error or "弹幕采集启动失败"
                if self.stop_live():
                    self.last_error = error
                return False
        return True

    def _feed_script_audio(self, runtime, items, params):
        clips = cycle(items)
        if params is None:
            next(clips)
        try:
            while not self._script_stop.wait(0.2):
                if runtime.get_queue_lengths().get("normal", 0) == 0:
                    item = next(clips)
                    text, product = item if params is not None and isinstance(item, tuple) else (item, None)
                    if product is not None:
                        self._sync_kt_product(product)
                    audio = text if params is None else self._synthesize(params, text)
                    if audio and not self._script_stop.is_set():
                        runtime.add_audio_to_queue(audio)
        except Exception as error:
            self.last_error = str(error)

    @staticmethod
    def _load_text_scripts(config):
        products = config.get("product_scripts") or config.get("products") or []
        scripts = [
            item.strip()
            for product in products if isinstance(product, dict)
            for item in (product.get("scripts") or [])
            if isinstance(item, str) and item.strip()
        ]
        return scripts or [
            item.strip() for item in (config.get("scripts") or [])
            if isinstance(item, str) and item.strip()
        ]

    @staticmethod
    def _load_text_script_items(config):
        products = config.get("product_scripts") or config.get("products") or []
        items = [
            (text.strip(), product)
            for product in products if isinstance(product, dict)
            for text in (product.get("scripts") or [])
            if isinstance(text, str) and text.strip()
        ]
        return items or [(text, None) for text in DigitalLiveManager._load_text_scripts(config)]

    def _prepare_kt_overlay(self, config, local_params):
        enabled = bool(config.get("enable_product_kt_follow", config.get("enableProductKtFollow", False)))
        from .product_kt_overlay import get_product_kt_overlay
        overlay = get_product_kt_overlay()
        overlay.set_enabled(False)
        overlay.clear()
        if not enabled:
            return
        from .digital_model_paths import resolve_character_dir
        model_dir = resolve_character_dir(self.config, self.runtime_dir, local_params.get("model_id"))
        hits = overlay.load_from_model_dir(model_dir)
        if hits <= 0:
            raise ValueError("当前形象没有识别到可用 KT 板，请重新制作形象")
        products = config.get("product_scripts") or config.get("products") or []
        first = next((item for item in products if isinstance(item, dict)), None)
        if first is not None:
            self._sync_kt_product(first)
        overlay.set_enabled(True)

    @staticmethod
    def _sync_kt_product(product):
        from .product_kt_overlay import get_product_kt_overlay
        overlay = get_product_kt_overlay()
        if not isinstance(product, dict):
            overlay.clear()
            return
        raw_id = product.get("goods_id") or product.get("goodsId") or product.get("item_id") or product.get("itemId") or 0
        try:
            goods_id = int(raw_id)
        except (TypeError, ValueError, OverflowError):
            goods_id = 0
        overlay.set_product_image(
            goods_id=goods_id,
            item_pic=product.get("item_pic") or product.get("itemPic") or "",
            item_name=product.get("name") or product.get("title") or product.get("item_name") or "",
        )

    @staticmethod
    def _close_kt_overlay():
        from .product_kt_overlay import close_product_kt_overlay
        close_product_kt_overlay()

    def _load_script_audio_files(self,audio_folder):
        if not audio_folder or not Path(audio_folder).is_dir():
            raise ValueError("请选择有效的话术音频目录")
        files = sorted(
            str(path) for path in Path(audio_folder).iterdir()
            if path.is_file() and path.suffix.lower() == ".wav"
        )
        if not files:
            raise ValueError("话术音频目录内未找到 WAV 文件")
        return files

    def request_manual_speak(self, text):
        return self._queue_manual_task(text, None)

    def request_simulated_question(self, text):
        return self._queue_manual_task(text, "模拟观众")

    def start_danmu(self, live_url, platform_type="douyin", on_message=None):
        if not self.is_broadcasting:
            return False
        with self._danmu_lock:
            if self._danmu_worker is not None and self._danmu_worker.is_alive():
                return False
            stale = self._danmu_capture is not None
        if stale:
            self.stop_danmu()
        capture = None
        try:
            bridge_url = self.config.get("danmu_bridge_url")
            if bridge_url:
                capture = DanmuBridge(bridge_url)
            elif platform_type not in _NON_OCR_PLATFORMS:
                capture = OCRDanmuBridge(platform_type)
            elif platform_type == "kuaishou":
                capture = KuaishouDanmuBridge(live_url)
            elif platform_type in ("pinduoduo", "pdd"):
                capture = PinduoduoDanmuBridge(live_url)
            elif platform_type == "taobao":
                from .taobao_control_capture import TaobaoControlDanmuCapture
                from .taobao_live_control import taobao_storage_path

                storage_state = self.config.get("taobao_storage_state")
                if storage_state is None:
                    saved_state = taobao_storage_path(self.runtime_dir)
                    if saved_state.is_file():
                        storage_state = saved_state
                capture = TaobaoControlDanmuCapture._configured(storage_state=storage_state)
            elif platform_type == "shopee":
                from .shopee_control_capture import ShopeeControlDanmuCapture

                capture = ShopeeControlDanmuCapture()
            else:
                try:
                    from .ws_capture import BarrageCapture
                except ImportError:
                    from tools.danmu_capture.ws_capture import BarrageCapture

                capture = BarrageCapture(platform_type=platform_type, url=live_url)
            capture.start()
            with self._danmu_lock:
                self._danmu_capture = capture
                self._danmu_on_message = on_message
                self._danmu_worker = Thread(target=self._danmu_loop, name="DigitalLiveManager.danmu", daemon=True)
                self._danmu_worker.start()
            return True
        except Exception as error:
            self.last_error = str(error)
            if capture is not None:
                try: capture.stop()
                except Exception: pass
            with self._danmu_lock:
                if self._danmu_capture is capture:
                    self._danmu_capture = None
                    self._danmu_worker = None
                    self._danmu_on_message = None
            return False

    def _danmu_loop(self):
        capture = self._danmu_capture
        on_message = self._danmu_on_message
        if capture is None: return
        try:
            messages = iter(capture)
            try:
                for message in messages:
                    if self._danmu_capture is not capture:
                        return
                    self.submit_danmu(message)
                    if on_message is not None:
                        on_message(message)
            finally:
                close = getattr(messages, "close", None)
                if callable(close):
                    close()
        except Exception as error:
            if self._danmu_capture is capture:
                self.last_error = str(error)
        finally:
            try: capture.stop()
            except Exception as error:
                if self._danmu_capture is capture:
                    self.last_error = str(error)
            with self._danmu_lock:
                if self._danmu_capture is capture:
                    self._danmu_capture = None
                    self._danmu_on_message = None
                    self._danmu_worker = None

    def stop_danmu(self):
        with self._danmu_lock:
            capture = self._danmu_capture
            worker = self._danmu_worker
            self._danmu_capture = None
            self._danmu_on_message = None
            self._danmu_worker = None
        if capture is None:
            return True
        success = True
        try:
            capture.stop()
        except Exception as error:
            self.last_error = str(error)
            success = False
        if worker is not None and worker is not current_thread() and worker.is_alive():
            worker.join(timeout=2)
        return success

    def submit_danmu(self, message):
        data = message.get("Data")
        if isinstance(data, dict):
            user = data.get("User")
            event_code = message.get("Type")
            kind = _BRIDGE_EVENT_TYPES.get(event_code, "") if type(event_code) is int else ""
            message = {
                "type": kind,
                "content": data.get("Content"),
                "nickname": user.get("Nickname") if isinstance(user, dict) else None,
            }
        kind = str(message.get("msg_type") or message.get("type") or "").strip().lower()
        event = kind if kind in {"enter", "follow", "gift", "like"} else None
        content = message.get("content") or message.get("text") or event
        if isinstance(content, str):
            nickname = str(message.get("nickname") or message.get("username") or "").strip() or "观众"
            if is_user_blocked(nickname, self.config.get("blocked_users") or ()):
                return
            self._queue_manual_task(content, nickname, event, captured=True)

    def _queue_manual_task(self, text, nickname, event=None, *, captured=False):
        text = text.strip()
        with self._manual_lock:
            runtime = self._runtime
            if runtime is None or not text or self._script_stop.is_set():
                return False
            if captured:
                if event == "enter" and nickname in self._welcomed_nicknames:
                    return False
                kind = "entrance" if event == "enter" else event or "comment"
                config = self._local_params["interaction_config"]
                try:
                    interval = float(config.get(f"{kind}_reply_interval") or 0)
                except (TypeError, ValueError):
                    interval = 0
                now = monotonic()
                last = self._last_interaction.get(kind)
                if last is not None and now - last < interval:
                    return False
                self._last_interaction[kind] = now
                if event == "enter":
                    self._welcomed_nicknames.add(nickname)
            if self._manual_queue is None:
                self._manual_queue = Queue()
                Thread(
                    target=self._manual_loop,
                    args=(runtime, self._local_params, self._manual_queue),
                    daemon=True,
                ).start()
            self._manual_queue.put((text, nickname, event))
        return True

    def _manual_loop(self, runtime, params, queue):
        while True:
            task = queue.get()
            with self._manual_lock:
                if queue is not self._manual_queue:
                    return
            if task is None:
                return
            text, nickname, event = task
            self._speak(runtime, params, text, queue, nickname, event)

    def _speak(self, runtime, params, text, queue, nickname=None, event=None):
        try:
            if nickname is not None:
                if contains_blocked(text, self.config.get("question_blocked_keywords") or ()):
                    return
                qa_info = params["qa_info"]
                qa_pairs = parse_qa_info_from_text(qa_info) if isinstance(qa_info, str) else qa_info
                reply = match_keywords(text, parse_qa_info(qa_pairs)) if isinstance(qa_pairs, list) else None
                if reply is None:
                    from .llm_reply import _generate_text_reply
                    reply = _generate_text_reply(
                        nickname, text, params["product_info"], params["qa_info"],
                        config=params["llm_config"], language=params.get("language", "zh-CN"),
                        **({"event": event} if event else {}),
                    )
                text = reply
                if not text or contains_blocked(text, self.config.get("reply_blocked_keywords") or ()):
                    return
            text = strip_prohibited_words(text, self.config.get("prohibited_words") or ())
            if not text.strip():
                return
            audio = self._synthesize(params, text)
            with self._manual_lock:
                if audio and queue is self._manual_queue:
                    runtime.add_audio_to_queue(audio, queue_name="danmu")
        except Exception as error:
            with self._manual_lock:
                if queue is self._manual_queue:
                    self.last_error = str(error)

    def _synthesize(self, params, text):
        voice = params["voice_general_config"]
        provider = (voice.get("provider") or "").strip().lower()
        if provider in {"minimax", "cosyvoice"}:
            synthesize = synthesize_speech_minimax if provider == "minimax" else synthesize_speech_cosyvoice
            return synthesize(
                text=text, voice_id=voice.get(f"{provider}_voice_id") or params["voice_id"],
                speed=params["voice_speed"], language=params.get("language", "zh-CN"),
                use_cache=params.get("use_audio_cache", True),
                **{f"{provider}_config": params[f"{provider}_voice_config"]},
            )
        return synthesize_local_audio(
                self.config, params["voice_id"], text, params["voice_speed"],
                params["voice_infer_version"],
            )

    def get_queue_lengths(self):
        runtime = self._runtime
        if runtime is None:
            return {}
        return dict(runtime.get_queue_lengths())

    def stop_live(self):
        if self._runtime is None:
            self._close_kt_overlay()
            return True
        if not self.stop_danmu():
            return False
        with self._manual_lock:
            self._script_stop.set()
            if self._manual_queue is not None:
                self._manual_queue.put(None)
                self._manual_queue = None
        if self._script_worker is not None:
            self._script_worker.join()
            self._script_worker = None
        try:
            self._runtime.stop_playing()
        except Exception as error:
            self.last_error = str(error)
            return False
        self._runtime = None
        self._close_kt_overlay()
        self.current_session_id = None
        self.last_error = None
        return True
