"""Recovered OCR-positioned live chat automation service."""

from __future__ import annotations

import json
import queue
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

from .auto_live_action_capture import CaptureWindow
from .auto_live_action_ocr import OCRProcessor
from .tools.customer_pack import is_vietnam_customer_pack

try:
    import pyautogui
    import pyperclip
except ImportError:
    pyautogui = None
    pyperclip = None
    print("Warning: pyautogui or pyperclip not installed. Visual control will not work.")


DEFAULT_CONFIG = {"send_interval": 60, "work_minutes": 10, "rest_minutes": 2,
                  "danmu_list": [], "random_send": False, "random_space": False,
                  "enable_text_reply": True}
_TOOLS_DIR = Path(__file__).resolve().parent / "tools"
CONFIG_PATH = _TOOLS_DIR / "auto_live_action" / "config" / "config.yaml"
CONTROL_UI_HTML = (_TOOLS_DIR / "auto_live_action" / "control_ui.html").read_text(
    encoding="utf-8").removesuffix("\n")
IS_VIETNAM_PACK = is_vietnam_customer_pack()
VIETNAM_UI_LABELS = {
    "title": "Trợ lý điều khiển live",
    "subtitle": "Dùng cho mọi nền tảng · Gửi bằng click mô phỏng",
    "save_config": "Lưu cấu hình",
    "usage_title": "Hướng dẫn",
    "usage_tip": ('Công cụ này gửi câu thoại bằng cách <b>chọn vùng màn hình</b> và '
                  '<b>mô phỏng click + gõ phím</b>, không cần đăng nhập, dùng được trên mọi nền tảng live.'
                  '<br>Quy trình: <b>① Bấm "Bắt đầu điều khiển"</b> → xuất hiện khung đỏ → '
                  '<b>② Kéo khung đỏ tới ô nhập bình luận</b> → <b>③ Bấm "Xác nhận vị trí"</b>, '
                  'hệ thống OCR sẽ nhận nút gửi (hỗ trợ "Gửi", "Send", "Submit"...) → '
                  '<b>④ Bắt đầu gửi câu thoại</b>.'),
    "script_title": "Cài đặt câu thoại",
    "send_interval": "Tần suất gửi (giây)",
    "work_minutes": "Thời gian chạy (phút)",
    "rest_minutes": "Thời gian nghỉ (phút)",
    "script_content": "Nội dung (mỗi dòng một câu)",
    "random_send": "Gửi ngẫu nhiên",
    "random_space": "Thêm khoảng trắng ngẫu nhiên",
    "enable_text_reply": "Bật trả lời thông minh",
    "confirm_position": "Xác nhận vị trí",
    "positioning_hint": ('Khung <b>đỏ</b> đã xuất hiện, hãy kéo tới <b>ô nhập bình luận/nút gửi</b> '
                         'rồi bấm <b>Xác nhận vị trí</b>.'),
    "stop_control": "Dừng điều khiển",
    "start_control": "Bắt đầu điều khiển",
    "stop_send": "Dừng gửi",
    "start_send": "Bắt đầu gửi",
    "control_positioning": 'Đang định vị: kéo khung đỏ tới ô nhập, rồi bấm "Xác nhận vị trí"',
    "control_running": "Điều khiển đã bật, đang chạy",
    "control_idle": "Chưa bật điều khiển",
    "danmu_running": "Đang gửi câu thoại",
    "danmu_idle": "Chưa gửi câu thoại",
    "saving_config": "Đang lưu cấu hình...",
    "save_success": "Lưu cấu hình thành công",
    "save_failed": "Lưu cấu hình thất bại",
    "recognizing_position": "Đang nhận vị trí...",
    "starting": "Đang khởi động...",
    "stopping": "Đang dừng...",
    "start_control_first": "Hãy bật điều khiển và xác nhận vị trí trước",
}
INPUT_HINT_KEYWORDS = ("说点什么", "输入", "评论", "comment", "nói gì", "noi gi",
                       "nhập", "viết", "bình luận", "binh luan")
SEND_BUTTON_KEYWORDS = ("发送", "send", "submit", "发布", "gửi")
FALLBACK_BTN_RIGHT_RATIO = 0.15


def _box_center(box):
    points = box or []
    return (round(sum(point[0] for point in points) / len(points)),
            round(sum(point[1] for point in points) / len(points))) if points else None


class VisualLiveAction:
    def __init__(self, target_coords):
        self.target_coords = target_coords

    def send_danmu(self, text):
        if not self.target_coords:
            print("未设置目标坐标")
            return None
        if not pyautogui:
            print("pyautogui 未安装")
            return None
        x, y = self.target_coords
        print(f"点击坐标: ({x}, {y}), 发送文本: {text}")
        pyautogui.click(x, y)
        time.sleep(0.2)
        pyperclip.copy(text)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        pyautogui.press("enter")
        return None

    def close(self):
        return None


class LiveControlAPI:
    def __init__(self):
        self.config = self.load_config()
        self.action_queue = queue.Queue()
        self.capture_cmd_queue, self.capture_res_queue = queue.Queue(), queue.Queue()
        self.capture_window = None
        self.capture_window_thread = None
        self.ocr_processor = None
        self.live_action = None
        self.positions = {}
        self.control_running = False
        self.is_positioning = False
        self.is_danmu_running = False
        self.control_thread = self.danmu_thread = None
        self.http_server = None
        self.http_server_thread = threading.Thread(
            target=self._run_http_server, daemon=True)
        self.http_server_thread.start()

    def load_config(self):
        value = dict(DEFAULT_CONFIG)
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as stream:
                loaded = yaml.safe_load(stream) or {}
            value.update(loaded)
        except FileNotFoundError:
            pass
        return value

    def save_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("w", encoding="utf-8") as stream:
            yaml.dump(self.config, stream, allow_unicode=True)

    def save_all_settings(self, settings):
        try:
            self._apply_settings(settings, persist=True)
            return {"success": True, "message": "配置已保存", "config": self.get_config()}
        except Exception as error:
            print(f"保存失败: {error}")
            return {"success": False, "message": f"保存配置失败: {error}",
                    "config": self.get_config()}

    def _apply_settings(self, settings, persist=False):
        self.config["danmu_list"] = [
            item.strip()
            for item in settings.get(
                "danmu_list", self.config.get("danmu_list", []))
            if item.strip()
        ]
        self.config["send_interval"] = max(
            1, int(settings.get(
                "send_interval", self.config.get("send_interval", 60))))
        self.config["work_minutes"] = max(
            1, int(settings.get(
                "work_minutes", self.config.get("work_minutes", 10))))
        self.config["rest_minutes"] = max(
            1, int(settings.get(
                "rest_minutes", self.config.get("rest_minutes", 2))))
        self.config["random_send"] = bool(settings.get(
            "random_send", self.config.get("random_send", False)))
        self.config["random_space"] = bool(settings.get(
            "random_space", self.config.get("random_space", False)))
        self.config["enable_text_reply"] = bool(settings.get(
            "enable_text_reply", self.config.get("enable_text_reply", True)))
        if persist:
            self.save_config()

    def get_config(self):
        return {
            "danmu_list": self.config.get("danmu_list", []),
            "random_send": self.config.get("random_send", False),
            "random_space": self.config.get("random_space", False),
            "rest_minutes": self.config.get("rest_minutes", 2),
            "send_interval": self.config.get("send_interval", 60),
            "work_minutes": self.config.get("work_minutes", 10),
            "enable_text_reply": self.config.get("enable_text_reply", True),
            "is_control_running": self.control_running,
            "is_danmu_running": self.is_danmu_running,
            "is_positioning": self.is_positioning,
            "vietnam_pack": IS_VIETNAM_PACK,
            "ui_labels": VIETNAM_UI_LABELS if IS_VIETNAM_PACK else None,
        }

    def update_config(self, new_config):
        for key, value in new_config.items():
            if key in self.config:
                self.config[key] = value
        self.save_config()
        return self.get_config()

    def start_positioning(self):
        if self.is_positioning:
            return {"success": False, "message": "正在定位中...",
                    "config": self.get_config()}
        try:
            with self.capture_cmd_queue.mutex:
                self.capture_cmd_queue.queue.clear()
            with self.capture_res_queue.mutex:
                self.capture_res_queue.queue.clear()
            self.capture_window_thread = threading.Thread(
                target=self._capture_window_worker, daemon=True)
            self.capture_window_thread.start()
            self.is_positioning = True
            print("启动定位模式...")
            return {
                "success": True,
                "message": "请将红色方框拖动到直播间评论输入框/发送按钮位置",
                "config": self.get_config(),
            }
        except Exception as error:
            self.is_positioning = False
            print(f"启动定位失败: {error}")
            return {"success": False, "message": f"启动定位失败: {error}",
                    "config": self.get_config()}

    def _capture_window_worker(self):
        try:
            self.capture_window = CaptureWindow(
                self.capture_cmd_queue, self.capture_res_queue)
            self.capture_window.run()
        except Exception as error:
            print(f"捕获窗口线程异常: {error}")

    def confirm_position(self):
        if not self.is_positioning:
            return {"success": False, "message": "定位窗口未启动",
                    "config": self.get_config()}
        try:
            self.capture_cmd_queue.put("capture")
            try:
                image = self.capture_res_queue.get(timeout=5)
            except queue.Empty:
                return {"success": False, "message": "获取截图超时",
                        "config": self.get_config()}
            self.ocr_processor = self.ocr_processor or OCRProcessor()
            ocr_results = self.ocr_processor.recognize_text(image)
            left, top, right, bottom = self.capture_window.rect()
            rect_width, rect_height = right - left, bottom - top
            input_hint = send_btn = None
            for item in ocr_results:
                item_text_lower = item["text"].lower()
                center = _box_center(item.get("box"))
                if not center:
                    continue
                target = (int(left + center[0]), int(top + center[1]))
                if any(key in item_text_lower for key in INPUT_HINT_KEYWORDS):
                    input_hint = target
                    print(f"OCR识别到输入提示文本，坐标: {input_hint}")
                if any(key in item_text_lower for key in SEND_BUTTON_KEYWORDS):
                    send_btn = target
                    print(f"OCR识别到发送按钮（'{item['text']}'），坐标: {send_btn}")
            if send_btn is None:
                send_btn = (int(left + rect_width * (1 - FALLBACK_BTN_RIGHT_RATIO / 2)),
                            int(top + rect_height / 2))
                print(f"OCR未识别到发送按钮，回退至最右侧15%区域中心: {send_btn}")
            target = input_hint or send_btn
            self.positions = {"input_hint": input_hint, "send_btn": send_btn,
                              "target": target}
            self.live_action = VisualLiveAction(target)
            self.capture_cmd_queue.put("stop")
            self.is_positioning = False
            self.capture_window_thread = None
            self.start_control()
            return {"success": True, "message": "位置已确认，场控运行中",
                    "config": self.get_config()}
        except Exception as error:
            print(f"确认位置失败: {error}")
            return {"success": False, "message": f"确认失败: {error}",
                    "config": self.get_config()}

    def _control_worker(self):
        print("场控工作线程已启动。")
        live_action = self.live_action
        try:
            while self.control_running:
                try:
                    command = self.action_queue.get(timeout=1)
                    if command == "stop":
                        print("收到停止指令，正在关闭工作线程。")
                        break
                    method_name = command[0]
                    args = command[1:]
                    method = getattr(live_action, method_name, None)
                    if callable(method):
                        method(*args)
                    else:
                        print(f"未知的指令: {method_name}")
                except queue.Empty:
                    continue
                except Exception as error:
                    print(f"工作线程在执行指令时出错: {error}")
        finally:
            if live_action:
                live_action.close()
            print("场控工作线程已结束。")
            self.control_running = False

    def start_control(self):
        try:
            if self.control_running:
                return {"success": True, "message": "场控已在运行中",
                        "config": self.get_config()}
            if not self.live_action:
                print("启动场控：进入定位模式，等待用户框选输入框位置")
                return self.start_positioning()
            self.control_running = True
            self.control_thread = threading.Thread(
                target=self._control_worker, daemon=True)
            self.control_thread.start()
            return {"success": True, "message": "位置已确认，场控运行中",
                    "config": self.get_config()}
        except Exception as error:
            print(f"启动场控错误: {error}")
            return {"success": False, "message": f"启动失败: {error}",
                    "config": self.get_config()}

    def stop_control(self):
        try:
            print("正在停止场控...")
            if self.is_positioning:
                self.capture_cmd_queue.put("stop")
                self.is_positioning = False
            if self.control_running:
                self.control_running = False
                self.action_queue.put("stop")
                if self.control_thread and self.control_thread.is_alive():
                    self.control_thread.join(timeout=2)
                self.control_thread = None
            print("场控已停止。")
            return {"success": True, "message": "场控已停止。",
                    "config": self.get_config()}
        except Exception as error:
            print(f"停止场控错误: {error}")
            return {"success": False, "message": f"停止失败: {error}",
                    "config": self.get_config()}

    def start_danmu(self, settings):
        try:
            if not self.control_running:
                print("请先启动场控。")
                return {"success": False, "config": self.get_config()}
            self._apply_settings(settings, persist=True)
            danmu_list = self.config["danmu_list"]
            if not danmu_list:
                return {"success": False, "config": self.get_config()}
            self.is_danmu_running = True
            args = (
                danmu_list,
                self.config["send_interval"],
                self.config["work_minutes"],
                self.config["rest_minutes"],
                self.config["random_send"],
                self.config["random_space"],
            )
            self.danmu_thread = threading.Thread(
                target=self._danmu_thread, args=args, daemon=True)
            self.danmu_thread.start()
            return {"success": True, "config": self.get_config()}
        except Exception as error:
            print(f"启动话术发送错误: {error}")
            return {"success": False, "config": self.get_config()}

    def stop_danmu(self):
        self.is_danmu_running = False
        if self.danmu_thread:
            self.danmu_thread.join(timeout=1)
        return {"success": True, "config": self.get_config()}

    def _add_random_spaces(self, text):
        if len(text) < 6:
            return text
        positions = sorted(random.sample(range(1, len(text)), min(5, len(text) - 1)))
        chars = list(text)
        for position in positions:
            chars.insert(position, " " * random.choice([1, 2, 3]))
        return "".join(chars)

    def _danmu_thread(self, danmu_list, interval, work_minutes, rest_minutes, random_send, random_space):
        work_duration = work_minutes * 60
        rest_duration = rest_minutes * 60
        try:
            while self.is_danmu_running:
                work_start = time.time()
                while (time.time() - work_start < work_duration
                       and self.is_danmu_running):
                    if random_send:
                        text = random.choice(danmu_list)
                    else:
                        text = danmu_list[0]
                        danmu_list = danmu_list[1:] + [danmu_list[0]]
                    if random_space:
                        text = self._add_random_spaces(text)
                    try:
                        self.action_queue.put(("send_danmu", text))
                    except Exception as error:
                        print(f"放入话术指令时出错: {error}")
                    time.sleep(interval)
                if self.is_danmu_running:
                    time.sleep(rest_duration)
        except Exception as error:
            print(f"话术线程错误: {error}")

    def _run_http_server(self, port=12346):
        owner = self
        class RequestHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(length) or b"{}")
                if self.path != "/send_danmu" or not body.get("text"):
                    status, payload = 400, {
                        "status": "error", "message": "Missing 'text' field"}
                else:
                    text = body["text"]
                    print(f"[HTTP] 收到文本发送请求: {text}")
                    owner.action_queue.put(("send_danmu", text))
                    status, payload = 200, {"status": "success"}
                encoded = json.dumps(payload).encode(); self.send_response(status); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(encoded)
            def log_message(self, *args): pass
        try:
            self.http_server = HTTPServer(("127.0.0.1", port), RequestHandler)
            print(f"场控HTTP服务已启动，监听端口 {port}")
            self.http_server.serve_forever()
        except Exception as error:
            print(f"无法启动场控HTTP服务(端口{port}): {error}")

    def close(self):
        self.stop_danmu(); self.stop_control()
        if self.http_server:
            self.http_server.shutdown(); self.http_server.server_close(); self.http_server = None


def main():
    import webview
    api = LiveControlAPI()
    window_title = (VIETNAM_UI_LABELS["title"] if IS_VIETNAM_PACK
                    else "通用场控助手")
    window = webview.create_window(
        window_title, html=CONTROL_UI_HTML, js_api=api,
        width=550, height=780, resizable=True, text_select=True,
        background_color="#f0f2f5")

    def on_closed():
        api.stop_control()
        sys.exit(0)

    window.events.closed += on_closed
    webview.start(debug=False)


if __name__ == "__main__":
    main()
