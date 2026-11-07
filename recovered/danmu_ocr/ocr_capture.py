"""Recovered OCR capture API state and text processing."""

import json
from pathlib import Path
from threading import Event, Thread

from recovered.customer_pack import is_vietnam_customer_pack

from .dedup import indel_ratio, normalize_dedup_key
from .filter import DanmuFilter, clean_and_build_message
from .ocr_engine import OCRProcessor
from .platforms import normalize_platform
from .websocket_server import WebSocketServer


VIETNAM_UI_LABELS = {
    'page_title': 'OCR Bắt bình luận',
    'capture_mode': 'Chế độ bắt:',
    'mode_interval': 'Quét theo chu kỳ',
    'mode_threshold': 'Theo ngưỡng tương đồng',
    'platform_type': 'Nền tảng:',
    'platform_general': 'Chung / Khác',
    'platform_wework': 'WeCom',
    'platform_shopee': 'Shopee',
    'mode_desc_threshold': 'Chế độ ngưỡng tương đồng: chỉ quét khi khung bắt có thay đổi, tiết kiệm tài nguyên nhưng có thể bỏ sót. Nếu bình luận mới không được nhận, hãy hạ ngưỡng.',
    'mode_desc_interval': 'Chế độ quét theo chu kỳ: quét nội dung trong khung bắt theo khoảng thời gian đặt sẵn để trích xuất bình luận, tốn tài nguyên hơn.',
    'capture_interval': 'Khoảng cách quét:',
    'interval_option': '{value} giây',
    'similarity_threshold': 'Ngưỡng tương đồng (0.1-1.0):',
    'create_window': 'Tạo khung bắt',
    'start_capture': 'Bắt đầu bắt',
    'stop_capture': 'Dừng bắt',
}


class Api:
    def __init__(self, platform="general"):
        self.vietnam_pack = is_vietnam_customer_pack()
        self.filter = DanmuFilter(vietnam_pack=self.vietnam_pack)
        self.platform_type = self._normalize_platform(platform)
        self.capture_settings = {
            "mode": "interval",
            "interval": 2,
            "threshold": 0.9,
            "platform": self.platform_type,
        }

        self.danmu_history = set()
        self.window = None
        self.capture_window = None
        self._capture_stop = Event()
        self._capture_stop.set()
        self._capture_thread = None
        self.ocr = None
        self.ws_server = WebSocketServer(8888)
        self.ws_server.start()

    def _ui_label(self, key, default):
        if self.vietnam_pack:
            return VIETNAM_UI_LABELS.get(key, default)
        return default

    def _capture_button_js(self, running):
        if running:
            label = self._ui_label("stop_capture", "停止捕获")
        else:
            label = self._ui_label("start_capture", "开始捕获")
        return f"updateCaptureButtonText({json.dumps(label)})"

    def get_capture_settings(self):
        settings = self.capture_settings.copy()
        settings["ui_labels"] = VIETNAM_UI_LABELS.copy() if self.vietnam_pack else None
        return settings

    def update_capture_settings(self, settings):
        settings = dict(settings)
        if "platform" in settings:
            self.platform_type = self._normalize_platform(settings["platform"])
            settings["platform"] = self.platform_type
        self.capture_settings.update(settings)

    @staticmethod
    def _normalize_platform(platform):
        return normalize_platform(platform)

    def _normalize_dedup_key(self, text):
        return normalize_dedup_key(text, self.vietnam_pack)

    def create_window(self):
        if self.capture_window is not None:
            return
        from .ui.capture_window import CaptureWindow

        self.capture_window = CaptureWindow()
        Thread(target=self._run_capture_window, daemon=True).start()

    def _run_capture_window(self):
        capture = self.capture_window
        try:
            capture.run(on_ready=lambda: self._set_capture_button_enabled(True))
        finally:
            self._capture_stop.set()
            self.capture_window = None
            self._set_capture_button_enabled(False)

    def _set_capture_button_enabled(self, enabled):
        if self.window is not None:
            self.window.evaluate_js(f"updateCaptureButton({json.dumps(enabled)})")

    def toggle_capture(self):
        thread = self._capture_thread
        if thread is not None and thread.is_alive():
            self._capture_stop.set()
            return
        if self.capture_window is None or self.capture_window.root is None:
            return
        self._capture_stop.clear()
        self._capture_thread = Thread(target=self._capture_timer, daemon=True)
        self._capture_thread.start()

    def _capture_timer(self):
        try:
            if self.window is not None:
                self.window.evaluate_js(self._capture_button_js(True))
            while not self._capture_stop.is_set() and self.capture_window is not None:
                self.process_capture()
                settings = self.capture_settings
                delay = 0.5 if settings["mode"] == "threshold" else float(settings["interval"])
                self._capture_stop.wait(delay)
        finally:
            self._capture_stop.set()
            if self.window is not None:
                self.window.evaluate_js(self._capture_button_js(False))

    def _capture_texts(self):
        if self.capture_window is None:
            return []
        settings = self.capture_settings
        threshold = settings["threshold"] if settings["mode"] == "threshold" else None
        capture = self.capture_window.capture_screen(threshold)
        if capture["image"] is None or not capture["changed"]:
            return []
        if self.ocr is None:
            self.ocr = OCRProcessor()
        return self.ocr.recognize_text(capture["image"])

    def process_capture(self):
        if self.platform_type == "wework":
            self._process_wework_texts(self._capture_texts())
        elif self.platform_type == "shopee":
            self._process_shopee_texts(self._capture_texts())
        else:
            self._process_general_texts(self._capture_texts())

    def _process_general_texts(self, texts):
        facebook_messages = self.filter.try_parse_facebook_comments(texts)
        if facebook_messages:
            for message in facebook_messages:
                print(f"[Facebook] {message.get('username', '')}: {message.get('content', '')}")
                self._emit_danmu(message)
            return
        for text in texts:
            message = self.filter.process_message(text)
            if message:
                self._emit_danmu(message)

    def _process_wework_texts(self, texts):
        username = None
        for text in texts:
            header = self.filter.parse_wework_header(text)
            if header is not None:
                username = header[0]
            elif username is not None:
                message = clean_and_build_message(username, text)
                if message:
                    self._emit_danmu(message)
                username = None

    def _process_shopee_texts(self, texts):
        for text in texts:
            message = self.filter.process_shopee_message(text)
            if message:
                self._emit_danmu(message)

    def _emit_danmu(self, danmu_info):
        if self.platform_type == "shopee":
            key = str(danmu_info.get("raw_text") or danmu_info.get("content") or "")
            key = key.strip().lower()
            if not key or key in self.danmu_history:
                return
            self.danmu_history.add(key)
        else:

            key = self._normalize_dedup_key(danmu_info["username"] + danmu_info["content"])
            if any(indel_ratio(key, previous) >= 0.85 for previous in self.danmu_history):
                return
            self.danmu_history.add(key)
        if self.window is not None:
            display = f"{danmu_info['username']}: {danmu_info['content']}"
            self.window.evaluate_js(f"appendDanmu({json.dumps(display)})")
        self.ws_server.send_message(danmu_info)

    def _close(self):
        self._capture_stop.set()
        capture = self.capture_window
        try:
            if capture is not None and capture.root is not None:
                capture.root.after(0, capture.destroy)
        finally:
            self.ws_server.stop()


def start_window(platform="general"):
    import webview

    api = Api(platform)
    try:
        title = api._ui_label("page_title", "OCR弹幕捕获")
        page = Path(__file__).with_name("ui") / "ui.html"
        window = webview.create_window(title, page.as_uri(), js_api=api)
        api.window = window
        window.events.closed += api._close
        webview.start()
    finally:
        api._close()
