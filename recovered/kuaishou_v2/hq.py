"""Kuaishou room detail lookup for ordinary responses."""

from urllib.request import Request, urlopen
from urllib.parse import quote, urlencode, urlsplit
import json
from pathlib import Path
import subprocess
import hashlib
import random
import re
import time
import traceback
import uuid

def generate_did():
    return "web_" + "".join(random.choice("0123456789abcdef") for _ in range(32))
def generate_gpu_info():
    vendor = random.choice(["Intel", "NVIDIA", "AMD"])
    if vendor == "Intel":
        model = random.choice(["HD", "UHD", "Iris"])
        renderer = f"Intel(R) {model} Graphics {random.randint(500, 999)}"
    elif vendor == "NVIDIA":
        series = random.choice(["GTX", "RTX"])
        model = random.choice([1060, 1650, 1660, 2060, 3060, 3070, 4060])
        renderer = f"NVIDIA GeForce {series} {model}"
    else:
        series = random.choice(["Radeon", "Radeon RX"])
        model = random.choice([580, 590, 5500, 5700, 6600, 6700])
        renderer = f"AMD {series} {model}"

    direct3d = random.choice(["11", "12"])
    d3d_driver = (
        f"D3D{direct3d}-{random.randint(20, 31)}."
        f"{random.randint(0, 21)}.{random.randint(10000, 15000)}."
        f"{random.randint(1000, 9000)}"
    )
    result = {
        "glRenderer": random.choice(["WebKit WebGL", "Mozilla WebGL"]),
        "glVendor": random.choice(["WebKit", "Mozilla"]),
        "unmaskRenderer": (
            f"ANGLE ({vendor}, {renderer} Direct3D{direct3d} "
            f"vs_5_0 ps_5_0, {d3d_driver})"
        ),
        "unmaskVendor": f"Google Inc. ({vendor})",
    }
    return json.dumps(result)
def generate_browser_fingerprint():
    chrome_version = random.randint(95, 138)
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/"
        f"{chrome_version}.0.0.0 Safari/537.36"
    )
    width = random.choice([1920, 1680, 1440, 2560])
    height = random.choice([1080, 1050, 900, 1440])
    time_zone = random.choice(["UTC+8", "UTC+7", "UTC+9", "UTC-5", "UTC-4"])
    language = random.choice(["zh-CN", "en-US", "zh-TW", "ja-JP"])
    timestamp = int(time.time() * 1000)
    result = {
        "ua": user_agent,
        "userAgent": user_agent,
        "timeZone": time_zone,
        "language": language,
        "cpuCoreCnt": str(random.randint(4, 16)),
        "platform": "Win64",
        "resolution": f"{width},{height}",
        "pixelDepth": random.choice([24, 32]),
        "colorDepth": random.choice([24, 32]),
        "canvasGraph": generate_fingerprint(),
        "canvasGraphFingerPrint": generate_fingerprint(),
        "webglGraph": generate_fingerprint(),
        "webglGraphFingerPrint": generate_fingerprint(),
        "key1": generate_did(),
        "key2": timestamp,
        "key3": user_agent,
        "key5": language,
        "key7": width,
        "key8": height,
    }
    return result
def generate_fingerprint():
    value = str(random.random()) + str(time.time()) + str(random.randint(10000, 99999))
    return hashlib.md5(value.encode()).hexdigest()


class Generate_trajectory:
    """Generate the slider track used by Kuaishou's verification payload."""

    @staticmethod
    def get_slide_track(distance):
        if not isinstance(distance, int) or distance < 0:
            raise ValueError(f"distance类型必须是大于等于0的整数: {distance}")
        tracks = []
        current_x = random.randint(10, 30)
        current_y = random.randint(10, 30)
        current_time = 0
        tracks.append(f"{current_x}|{current_y}|0")
        series = random.randint(20, 30)
        for number in range(series):
            progress = number / series
            if progress < 0.3:
                factor = progress ** 3
            elif progress > 0.7:
                factor = (1 - progress) ** 2
            else:
                factor = 1
            x_increase = int(
                distance * factor / series * random.uniform(0.9, 1.1)
            )
            current_x = min(distance, current_x + x_increase)
            current_time += random.randint(10, 50)
            current_y += random.randint(-3, 3)
            tracks.append(f"{current_x}|{current_y}|{current_time}")
            if current_x == distance:
                break
        if current_x < distance:
            current_time += random.randint(10, 50)
            tracks.append(f"{distance}|{current_y}|{current_time}")
        return ",".join(tracks)


_ROOM_DETAIL_URL = "https://live.kuaishou.com/live_api/liveroom/livedetail"
_ORIGIN = "https://live.kuaishou.com"
_SIGN_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "yunchuang_v122/_internal/tools/danmu_capture/kuaishou_v2/js/sign_url.js"
)


class Tool:
    def __init__(self, liveUrl, cookie=None):
        self.liveUrl = liveUrl
        self.cookie = cookie
        try:
            import ddddocr
            self.det = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
        except ImportError:
            self.det = None
        self.verification_token = None
        if not self.cookie:
            self.cookie = self.generate_cookie()
        self.base_dir = str(Path(__file__).resolve().parent)
        self.node_exe = str(Path(self.base_dir) / "js" / "node.exe")
        self.sign_url_js = str(Path(self.base_dir) / "js" / "sign_url.js")
        self.encrypt_js = str(Path(self.base_dir) / "js" / "encrypt.js")

    def getLiveRoomId(self):
        import requests

        live_id = self.liveUrl.strip("/").split("/")[-1]
        params = {"principalId": live_id}
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Referer": self.liveUrl,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Cookie": self.cookie,
        }
        try:
            response = requests.get(_ROOM_DETAIL_URL, params=params, headers=headers)
            resp_json = response.json()
        except Exception:
            traceback.print_exc()
        live_stream = resp_json["data"]["liveStream"]
        return live_stream.get("liveStreamId") or live_stream.get("id")

    def generate_cookie(self):
        return "did=" + str(generate_did())

    def _slide_match(self, target_bytes, background_bytes, simple_target):
        if self.det is None:
            raise RuntimeError("快手验证码 OCR 未配置，请安装独立平台工具环境后重试")
        if simple_target:
            return self.det.slide_match(
                target_bytes, background_bytes, simple_target=True
            )
        return self.det.slide_match(target_bytes, background_bytes)

    def slide_match(self, target_bytes, background_bytes):
        return self._slide_match(target_bytes, background_bytes, True)

    def handle_captcha(self, resp_data):
        import requests

        for retry_count in range(3):
            try:
                captcha_url = resp_data.get("data", {}).get("captchaUrl")
                if not captcha_url:
                    print("未找到验证码URL")
                    return False
                captcha_session_match = re.search(
                    r"captchaSession=([^&]+)", captcha_url
                )
                if not captcha_session_match:
                    print("未找到captchaSession参数")
                    return False
                captcha_session = captcha_session_match.group(1)

                captcha_headers = {
                    "Connection": "keep-alive",
                    "Pragma": "no-cache",
                    "Cache-Control": "no-cache",
                    "sec-ch-ua": '"Chromium";v="21", " Not;A Brand";v="99"',
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "sec-ch-ua-mobile": "?0",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
                    "sec-ch-ua-platform": '"Windows"',
                    "Origin": "https://captcha.zt.kuaishou.com",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                    "Referer": (
                        "https://captcha.zt.kuaishou.com/iframe/index.html?captchaSession="
                        f"{captcha_session}&type=1&configUrl=https%3A%2F%2Fcaptcha.zt.kuaishou.com%2Frest%2Fzt%2Fcaptcha%2Fsliding%2Fconfig&bizName=ANTICRAWL_DEFAULT"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Cookie": self.cookie,
                }
                params = {"captchaSession": captcha_session}
                captcha_info_resp = requests.get(
                    "https://captcha.zt.kuaishou.com/rest/zt/captcha/sliding/config",
                    headers=captcha_headers,
                    params=params,
                )
                captcha_info = captcha_info_resp.json()
                if captcha_info.get("result") != 1:
                    print("获取验证码信息失败:", captcha_info)
                    return False

                captcha_sn = captcha_info["captchaSn"]
                bg_pic_url = captcha_info["bgPicUrl"]
                cut_pic_url = captcha_info["cutPicUrl"]
                dis_y = round(int(captcha_info["disY"]) * 0.469)
                image_params = {"captchaSn": captcha_sn}
                bg_img = requests.get(bg_pic_url, params=image_params).content
                cut_img = requests.get(cut_pic_url, params=image_params).content
                slide_result = self._slide_match(cut_img, bg_img, False)
                distance = int(round(int(slide_result["target"][0]) * 0.469))
                trajectory = Generate_trajectory().get_slide_track(
                    int(distance * 3.42)
                )
                browser_fingerprint = generate_browser_fingerprint()
                gpu_info = generate_gpu_info()
                captcha_data = {
                    "captchaSn": captcha_sn,
                    "bgDisWidth": 316,
                    "bgDisHeight": 184,
                    "cutDisWidth": 56,
                    "cutDisHeight": 56,
                    "relativeX": distance,
                    "relativeY": dis_y,
                    "trajectory": trajectory,
                    "gpuInfo": gpu_info,
                    "captchaExtraParam": json.dumps(browser_fingerprint),
                }
                data_crack = "&".join(
                    f"{key}={quote(str(value))}"
                    for key, value in captcha_data.items()
                ).replace("/", "%2F")
                verify_param = subprocess.check_output(
                    [self.node_exe, self.encrypt_js, data_crack],
                    encoding="utf-8",
                ).strip()

                verify_headers = {
                    "Connection": "keep-alive",
                    "Pragma": "no-cache",
                    "Cache-Control": "no-cache",
                    "sec-ch-ua": '"Chromium";v="21", " Not;A Brand";v="99"',
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "sec-ch-ua-mobile": "?0",
                    "User-Agent": browser_fingerprint["userAgent"],
                    "sec-ch-ua-platform": '"Windows"',
                    "Origin": "https://captcha.zt.kuaishou.com",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                    "Referer": (
                        "https://captcha.zt.kuaishou.com/iframe/index.html?captchaSession="
                        + captcha_session
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Cookie": self.cookie,
                }
                verify_result = requests.post(
                    "https://captcha.zt.kuaishou.com/rest/zt/captcha/sliding/kSecretApiVerify",
                    headers=verify_headers,
                    json={"verifyParam": verify_param},
                ).json()
                if verify_result.get("result") == 1:
                    print("验证码验证成功!")
                    if "captchaToken" in verify_result:
                        self.verification_token = verify_result["captchaToken"]
                    return True

                print(f"验证码验证失败 (尝试 {retry_count + 1}/3):", verify_result)
                if retry_count == 2:
                    print("已达到最大重试次数，验证失败")
                    return False
                print(f"准备第 {retry_count + 2} 次重试...")
                time.sleep(1)
            except Exception as exc:
                print(f"处理验证码时出错: {exc}")
                traceback.print_exc()
                if retry_count == 2:
                    print("已达到最大重试次数，验证失败")
                    return False
                print(f"准备第 {retry_count + 2} 次重试...")
                time.sleep(1)
        return False

    def processLiveId(self, live_id):
        import requests

        if not live_id:
            print("未获取到直播间ID，无法生成签名URL。")
            return None

        params = {"liveStreamId": live_id}
        signed_url = subprocess.check_output(
            [
                self.node_exe,
                self.sign_url_js,
                "/live_api/liveroom/websocketinfo",
                "/rest/k/live/websocket/info",
                json.dumps(params),
            ],
            encoding="utf-8",
        ).strip()
        websocketinfo_url = (
            f"https://live.kuaishou.com{signed_url}&liveStreamId={live_id}"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "kww": "PnGU+9+Y8008S+nH0U+0mjPf8fP08f+98f+nLlwnrIP9+Sw/ZFGfzY+eGlGf+f+e4SGfbYP0QfGnLFwBLU80mYGADl+9PlG9cUPn+SP/rl+eGMP0PIP/Z9P0qAPecFP0Hh80HI+nQ0+9pjPeDE8BHAPAqF+0ZAGncU+nr9wec9G/G=",
            "Cookie": self.cookie,
            "Referer": self.liveUrl,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Host": "live.kuaishou.com",
        }
        if self.verification_token:
            headers["identity-verification-token"] = self.verification_token
            headers["identity-verification-type"] = "1"

        response = requests.get(websocketinfo_url, headers=headers)
        json_data = response.json()
        resp_data = json_data.get("data", {})
        if resp_data.get("result") == 400002:
            captcha_result = self.handle_captcha(resp_data)
            if captcha_result and self.verification_token:
                headers["identity-verification-token"] = self.verification_token
                headers["identity-verification-type"] = "1"
                response = requests.get(websocketinfo_url, headers=headers)
                json_data = response.json()
        return json_data

    def _request_json(self, endpoint, **params):
        headers = {
            "Origin": _ORIGIN,
            "Referer": self.liveUrl,
            "Accept": "application/json",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        query = urlencode(params)
        url = f"{endpoint}?{query}" if query else endpoint
        request = Request(url, headers=headers)
        with urlopen(request, timeout=10) as response:
            return json.load(response)


def sign_websocket_path(node, script: Path, params):
    return subprocess.check_output(
        [node, str(script), "/live_api/liveroom/websocketinfo",
         "/rest/k/live/websocket/info", json.dumps(params)],
        encoding="utf-8",
        timeout=10,
    ).strip()
