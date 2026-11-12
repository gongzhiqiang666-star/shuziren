"""DOM comment extraction recovered from the Taobao control extension."""

import json
import os
import shutil
from pathlib import Path
import re
import time
from queue import Empty, Queue
from threading import Event, RLock, Thread, current_thread
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

_EXPLAIN_WATCH_SEC = 3.0
_CONTROL_RECOVER_COOLDOWN_SEC = 2.0
_CONTROL_RECOVER_SLOW_SEC = 10.0
_CONTROL_RECOVER_MAX_STREAK = 3
_PAGE_RECYCLE_INTERVAL_SEC = 30.0
_MIN_POPUP_INTERVAL_SEC = 5.0
GOODS_ITEM_SELECTOR = ".tcp-commodity-item"
COMMENT_ITEM_SELECTOR = ".tc-comment-item"
# Recovered from the Cython module initialiser: cached integer slot 0x1910 is
# assigned to the public ``COMMENT_MAX_LEN`` name.
COMMENT_MAX_LEN = 50

_COMMENT_SCRIPT = r"""() => {
  const items = Array.from(document.querySelectorAll('.tc-comment-item'));
  return items.map((el) => {
    const nameEl = el.querySelector('.tc-comment-item-userinfo-name');
    const tagEl = el.querySelector('.tc-comment-item-userinfo-tag');
    const timeEl = el.querySelector('.alpw-comment-time');
    const contentEl = el.querySelector('.tc-comment-item-content');
    const nickname = ((nameEl && nameEl.innerText) || '').replace(/\s+/g, ' ').trim();
    const tag = ((tagEl && tagEl.innerText) || '').replace(/\s+/g, ' ').trim();
    const time = ((timeEl && timeEl.innerText) || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
    const content = ((contentEl && contentEl.innerText) || '').replace(/\s+/g, ' ').trim();
    return { nickname, tag, time, content };
  }).filter((x) => x.content);
}
"""


_COMMODITY_SCRIPT = r"""() => {
              const nodes = Array.from(document.querySelectorAll('.tcp-commodity-item'));
              return nodes.map((el, idx) => {
                const text = (el.innerText || '').trim().replace(/\s+/g, ' ');
                const idMatch = text.match(/ID[:：\s]*(\d{5,})/i);
                const priceMatch = text.match(/[￥¥]\s*([0-9]+(?:\.[0-9]+)?)/);
                let name = text
                  .replace(/ID[:：\s]*\d{5,}/ig, ' ')
                  .replace(/[￥¥]\s*[0-9]+(?:\.[0-9]+)?/g, ' ')
                  .replace(/选择分组|设置利益点|删除商品/g, ' ')
                  .replace(/\s+/g, ' ')
                  .trim();
                return {
                  itemId: idMatch ? idMatch[1] : '',
                  itemName: name,
                  itemPrice: priceMatch ? priceMatch[1] : '',
                  itemPic: (() => {
                    const img = el.querySelector('img.tcp-commodity-item-img-inner, img');
                    let src = (img && (img.getAttribute('src') || img.getAttribute('data-src'))) || '';
                    if (src.startsWith('//')) src = 'https:' + src;
                    return src;
                  })(),
                  itemUrl: idMatch ? ('https://item.taobao.com/item.htm?id=' + idMatch[1]) : '',
                  sellerId: '',
                  goodsIndex: idx + 1,
                };
              });
            }"""


_LIVE_ID_SCRIPT = r"""() => {
              const cards = Array.from(document.querySelectorAll('.tblalm-lm-list-item-live'));
              for (const el of cards) {
                const text = ((el.innerText || '') + '').replace(/\s+/g, ' ');
                if (!text.includes('未开播')) continue;
                const idMatch = text.match(/ID\s*(\d{6,})/i);
                if (idMatch) return idMatch[1];
              }
              return '';
            }"""


_COMMENT_INPUT_SCRIPT = r"""(text) => {
  const el = document.querySelector('#comment-page textarea.tc-textarea')
    || document.querySelector('.tc-comment-reply textarea');
  if (!el) return { ok: false, reason: 'no textarea' };
  el.focus();
  const proto = window.HTMLTextAreaElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, 'value');
  if (desc && desc.set) desc.set.call(el, text);
  else el.value = text;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, value: el.value || '', len: (el.value || '').length };
}
"""


_JSONP_RE = re.compile(r"^[^(]+\((.*)\)\s*$", re.DOTALL)


def _decode_cookie_value(raw):
    value = "" if raw is None else str(raw)
    try:
        value = unquote(value)
    except (TypeError, ValueError):
        pass
    if "\\u" in value or "\\x" in value:
        try:
            value = value.encode("latin1").decode("unicode_escape")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return value.strip()


def _read_nick_from_storage() -> str:
    return str(_get_taobao_account_status(Path.cwd()).get("nick") or "").strip()


def _browser_context_kwargs(*, use_storage=True):
    kwargs = {"viewport": {"width": 1440, "height": 900}}
    storage = taobao_storage_path(Path.cwd())
    if use_storage and storage.is_file():
        kwargs["storage_state"] = str(storage)
    return kwargs


def _resolve_chrome_path() -> str:
    candidates = [
        os.environ.get("CHROME_PATH"), shutil.which("chrome"), shutil.which("google-chrome"),
        shutil.which("chromium"), shutil.which("microsoft-edge"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    return next((str(Path(path)) for path in candidates if path and Path(path).is_file()), "")


def _mid_control_busy() -> bool:
    controller = globals().get("_controller")
    thread = getattr(controller, "_thread", None) if controller is not None else None
    return bool(thread is not None and thread.is_alive() and current_thread() is not thread)


def _dismiss_live_plan_overlays(page) -> None:
    if page is None:
        return
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    selector = ".driver-popover button, .ant-modal button, [role='dialog'] button, .tbla-modal-wrap button"
    try:
        buttons = page.locator(selector)
        for index in range(min(buttons.count(), 20)):
            button = buttons.nth(index)
            try:
                text = str(button.inner_text() or "").strip()
                if button.is_visible() and (not text or any(word in text for word in ("关闭","取消","跳过","知道了","我知道了"))):
                    button.click(timeout=1000)
            except Exception:
                continue
    except Exception:
        pass


def _parse_live_item_list(payload):
    """Normalize the several list envelopes returned by Taobao's live APIs."""
    current = payload
    if isinstance(current, str):
        try: current = _parse_jsonp_or_json(current)
        except (TypeError, ValueError, json.JSONDecodeError): return []
    for _ in range(8):
        if isinstance(current, list):
            return [item for item in current if isinstance(item, dict)]
        if not isinstance(current, dict):
            return []
        found = next((current.get(key) for key in ("lives","list","items","result","data","rows")
                      if isinstance(current.get(key), (list, dict))), None)
        if found is None:
            return []
        current = found
    return []


def _pick_latest_unpublished_live(lives):
    candidates = []
    for index, item in enumerate(lives or []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("room_status") or item.get("roomStatus") or item.get("status") or "").strip().lower()
        living = item.get("living")
        unpublished = living in (False, 0, "0", "false", None) and status not in {"living","live","1","2","直播中"}
        unpublished = unpublished or status in {"未开播","unpublished","not_started","preparing","0"}
        if not unpublished:
            continue
        timestamp = item.get("startTime") or item.get("start_time") or item.get("createTime") or item.get("gmtCreate") or ""
        candidates.append((str(timestamp), index, item))
    return max(candidates, default=("", -1, None), key=lambda row: (row[0], row[1]))[2]


def _wait_taobao_login(page, *, target_url):
    return _wait_taobao_login_with_cancel(page, target_url=target_url, timeout_sec=600, cancel=None)


def _wait_taobao_login_with_cancel(page, *, target_url, timeout_sec, cancel):
    if page is None:
        raise RuntimeError("Taobao page is unavailable")
    target_host = urlsplit(target_url).hostname
    if cancel is None:
        page.wait_for_url(lambda url: urlsplit(str(url)).hostname == target_host, timeout=timeout_sec * 1000)
    else:
        deadline = time.monotonic() + timeout_sec
        while urlsplit(page.url).hostname != target_host:
            if cancel.is_set():
                raise InterruptedError('淘宝登录已取消')
            if time.monotonic() >= deadline:
                raise TimeoutError('淘宝登录超时')
            page.wait_for_timeout(250)
        if cancel.is_set():
            raise InterruptedError('淘宝登录已取消')
    _dismiss_live_plan_overlays(page)
    return None


def _parse_jsonp_or_json(text):
    text = text.strip()
    wrapper = _JSONP_RE.fullmatch(text)
    return json.loads(wrapper.group(1) if wrapper else text)


def _mtop_payload(resp):
    return _parse_jsonp_or_json(resp.text())


def _normalize_product_item(raw, fallback_index):
    if not isinstance(raw, dict):
        return None
    item_id = str(raw.get("itemId") or raw.get("item_id") or "").strip()
    if not item_id:
        return None
    name = str(raw.get("itemName") or raw.get("item_name") or raw.get("title") or "").strip()
    price = raw.get("itemPrice")
    if price is None or price == "":
        price = raw.get("item_price")
    image = str(raw.get("itemPic") or raw.get("item_pic") or "").strip()
    if image.startswith("//"):
        image = "https:" + image
    item_url = str(raw.get("itemUrl") or raw.get("item_url") or "").strip()
    index = raw.get("goodsIndex") or raw.get("goods_index") or fallback_index
    try:
        index = int(index)
    except (TypeError, ValueError, OverflowError):
        index = fallback_index
    return {
        "itemId": item_id,
        "itemName": name,
        "itemPrice": "" if price is None else str(price).strip(),
        "itemPic": image,
        "itemUrl": item_url or f"https://item.taobao.com/item.htm?id={item_id}",
        "sellerId": str(raw.get("sellerId") or raw.get("seller_id") or "").strip(),
        "goodsIndex": index,
    }


def _favorite_response_items(response):
    if "mtop.taobao.dreamweb.favorites.item.query" not in response.url:
        return None
    payload = _mtop_payload(response)
    for _ in range(2):
        if not isinstance(payload, dict):
            return None
        payload = payload.get("data")
    if not isinstance(payload, dict):
        return None
    items = payload.get("result")
    return items if isinstance(items, list) else None


def _scrape_commodity_dom(page):
    return page.evaluate(_COMMODITY_SCRIPT)


def _scrape_unpublished_live_id(page):
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        result = page.wait_for_function(_LIVE_ID_SCRIPT, timeout=15000)
    except PlaywrightTimeoutError:
        if urlsplit(page.url).hostname == "login.taobao.com":
            raise TaobaoLoginRequired("淘宝登录已失效，请重新登录")
        return ""
    try:
        return result.json_value()
    finally:
        result.dispose()


def _is_control_url(url, live_id=""):
    parsed = urlsplit(url)
    if parsed.hostname != "liveplatform.taobao.com" or not parsed.path.rstrip("/").endswith("/live/control"):
        return False
    ids = parse_qs(parsed.query, keep_blank_values=True).get("liveId", [])
    if len(ids) != 1:
        return False
    current_id = ids[0]
    return current_id.isascii() and current_id.isdecimal() and (
        not live_id or current_id == live_id
    )


def taobao_storage_path(runtime_dir):
    return Path(runtime_dir) / "tools/auto_live_action/user_data/taobao_storage.json"

def clear_taobao_storage():
    for root in (Path.cwd(),Path(__file__).resolve().parent.parent):
        try: taobao_storage_path(root).unlink(missing_ok=True)
        except OSError: pass

def format_taobao_product_content(item):
    name=str(item.get("itemName") or item.get("name") or "商品").strip()
    price=str(item.get("itemPrice") or item.get("price") or "").strip()
    return f"{name}，价格{price}元" if price else name


def _get_taobao_account_status(runtime_dir, storage_state=None):
    if not isinstance(storage_state, dict):
        path = Path(storage_state) if storage_state is not None else taobao_storage_path(runtime_dir)
        try:
            storage_state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            storage_state = None
    cookies = storage_state.get("cookies", []) if isinstance(storage_state, dict) else []
    names = {
        cookie.get("name"): cookie.get("value")
        for cookie in cookies
        if isinstance(cookie, dict)
    } if isinstance(cookies, list) else {}
    nick = _decode_cookie_value(names.get("tracknick") or names.get("lgc") or names.get("dnk") or names.get("_nk_") or "")
    return {"has_storage": isinstance(storage_state, dict), "nick": nick, "logged_in": bool(nick)}


def get_taobao_account_status():
    return _get_taobao_account_status(Path.cwd())


class TaobaoLoginRequired(RuntimeError):
    pass


class TaobaoLiveControl:
    def __init__(self):
        self._initialize()

    @classmethod
    def _create(cls, page=None, *, runtime_dir=None):
        instance=cls.__new__(cls); instance._initialize(page,runtime_dir); return instance

    def _initialize(self, page=None, runtime_dir=None):
        self._page = page
        self._storage_path = taobao_storage_path(runtime_dir) if runtime_dir is not None else None
        self._playwright = None
        self._browser = None
        self._context = None
        self._live_id = None
        self._lock = RLock(); self._active_goods_id = None; self._popup_interval_sec = 30.0; self._last_popup_at = 0.0
        self._popup_pending = False
        self._explain_watch_until = 0.0
        self._explain_fail_streak = 0
        self._control_recover_streak = 0
        self._control_recover_at = 0.0
        self._page_ready_at = 0.0
        self._initializing = False
        self._actions = Queue(); self._stop_event = Event(); self._thread = None

    def connected(self):
        return self._is_page_alive()

    def _on_worker(self): return self._thread is not None and current_thread() is self._thread
    def ensure_worker(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive(): return self._thread
            self._stop_event.clear(); self._thread=Thread(target=self._worker_loop,name="taobao-live-control",daemon=True); self._thread.start(); return self._thread
    def _call(self,action,timeout=180.0,**payload):
        if self._on_worker(): return self._handle_action(action,payload)
        self.ensure_worker(); done=Event(); request={"action":action,"payload":payload,"done":done}
        self._actions.put(request)
        if not done.wait(timeout): raise TimeoutError(f"Taobao action timed out: {action}")
        if request.get("error") is not None: raise request["error"]
        return request.get("result")
    def _post(self,action,**payload):
        self.ensure_worker(); self._actions.put({"action":action,"payload":payload})
    def _handle_action(self,action,payload):
        if action=="connect": return self._connect_direct(headless=bool(payload.get("headless")))
        if action=="connect_configured": return self._connect_direct(**payload)
        if action=="fetch_comments": return self._do_fetch_comments()
        if action=="open_control_page": return self.open_control_page(payload.get("live_id"))
        if action=="send_comment": return self._do_send_comment(payload.get("text",""))
        if action=="popup": return self._do_popup(int(payload["goods_id"]))
        if action=="set_active_goods": return self._set_active_goods_direct(int(payload["goods_id"]),float(payload.get("interval_sec",30.0)))
        if action=="clear_active_goods": return self._clear_active_goods_direct()
        if action=="login": return self.login(**payload)
        if action=="_invoke": return payload["callback"]()
        if action=="disconnect":
            self._stop_explain_cycle(reason="disconnect")
            self._safe_close_browser()
            self._initializing=False
            return True
        raise ValueError(f"unknown Taobao action: {action}")

    def ensure_connected(self, *, headless=False):
        return self.connect(headless=headless)

    def disconnect(self):
        if not self._on_worker(): return self._call("disconnect")
        self._stop_explain_cycle(reason="disconnect")
        self._safe_close_browser()
        self._initializing=False

    def shutdown(self):
        try:
            if self._thread and self._thread.is_alive(): self._call("disconnect",timeout=10)
            else: self.close()
        finally:
            self._stop_event.set(); self._actions.put(None)
            thread=self._thread
            if thread and thread.is_alive() and thread is not current_thread(): thread.join(timeout=5)
            self._thread=None

    def connect(self, *, headless=False):
        if not self._on_worker(): return self._call("connect",headless=headless)
        return self._connect_direct(headless=headless)

    def _connect_configured(self, *, headless=False, storage_state=None, executable_path=None):
        if not self._on_worker(): return self._call("connect_configured",headless=headless,storage_state=storage_state,executable_path=executable_path)
        return self._connect_direct(headless=headless,storage_state=storage_state,executable_path=executable_path)

    def _connect_direct(self, *, headless=False, storage_state=None, executable_path=None):
        if self.connected():
            return True
        if self._page is not None:
            self.close()

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        try:
            options = {"headless": headless, "args": ["--disable-blink-features=AutomationControlled"]}
            if executable_path is not None:
                options["executable_path"] = executable_path
            elif (detected_chrome := _resolve_chrome_path()):
                options["executable_path"] = detected_chrome
            self._browser = self._playwright.chromium.launch(**options)
            if storage_state is None and self._storage_path is not None and self._storage_path.is_file():
                storage_state = self._storage_path
            context_options = _browser_context_kwargs(use_storage=False)
            if storage_state is not None:
                context_options["storage_state"] = storage_state
            self._context = self._browser.new_context(**context_options)
            self._page = self._context.new_page()
        except BaseException:
            self.close()
            raise
        return True

    def login(self, *, storage_path=None, login_timeout_sec=600, force_relogin=False, cancel=None):
        if not self._on_worker():
            return self._call("login",timeout=float(login_timeout_sec)+45,storage_path=storage_path,login_timeout_sec=login_timeout_sec,force_relogin=force_relogin,cancel=cancel)
        if storage_path is None:
            storage_path = self._storage_path
        if storage_path is None:
            raise ValueError("Provide storage_path or initialize with runtime_dir")
        if force_relogin:
            self.close()
        saved_state = Path(storage_path)
        self._storage_path = saved_state
        if force_relogin:
            self._connect_configured(storage_state={"cookies": [], "origins": []})
        else:
            self._connect_configured(storage_state=saved_state if saved_state.is_file() else None)
        target = "https://liveplatform.taobao.com/restful/index/live/list"
        login_query = urlencode({"bizName": "taobao", "sub": "true", "redirectURL": target})
        self._page.goto("https://login.taobao.com/havanaone/login/login.htm?" + login_query)
        _wait_taobao_login_with_cancel(self._page, target_url=target, timeout_sec=login_timeout_sec, cancel=cancel)
        self._save_storage_state()

    def _save_storage_state(self):
        if self._page is None:
            raise RuntimeError("Taobao browser session is not connected")
        if self._storage_path is None:
            raise ValueError("Taobao storage state path is not configured")
        target = Path(self._storage_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        return self._page.context.storage_state(path=str(target))

    def close(self):
        self._page = None
        browser, self._browser = self._browser, None
        context, self._context = self._context, None
        playwright, self._playwright = self._playwright, None
        try:
            if context is not None:
                context.close()
        finally:
            try:
                if browser is not None:
                    browser.close()
            finally:
                if playwright is not None:
                    playwright.stop()

    def _is_page_alive(self):
        return self._page is not None and not self._page.is_closed()

    def fetch_comments(self):
        if not self._on_worker(): return self._call("fetch_comments")
        if not self._is_page_alive():
            raise RuntimeError("Taobao browser session is not connected")
        if not self.open_control_page(self._live_id):
            raise RuntimeError("Taobao live control page unavailable")
        self._ensure_comment_panel(self._page)
        return self._page.evaluate(_COMMENT_SCRIPT)

    def _do_fetch_comments(self): return self.fetch_comments()

    def send_comment(self, text):
        if not self._on_worker(): return self._call("send_comment",text=text)
        if not isinstance(text, str) or not text.strip():
            return False
        if not self.connected() or not self.open_control_page(self._live_id):
            return False
        self._ensure_comment_panel(self._page)
        result = self._page.evaluate(_COMMENT_INPUT_SCRIPT, text)
        if not result["ok"]:
            return False
        self._page.locator(".tc-comment-reply-publish-button").first.click(timeout=15000)
        return True
    def _do_send_comment(self,text): return self.send_comment(text)

    def popup(self,goods_id): return self._call("popup",goods_id=int(goods_id))
    def set_active_goods(self,goods_id,*,interval_sec=30.0):
        return self._call("set_active_goods",goods_id=int(goods_id),interval_sec=float(interval_sec))
    def _set_active_goods_direct(self,goods_id,interval_sec):
        self._popup_interval_sec=max(_MIN_POPUP_INTERVAL_SEC,float(interval_sec))
        self._active_goods_id=int(goods_id)
        self._popup_pending=True
        self._explain_fail_streak=0
        self._control_recover_streak=0
        return True
    def clear_active_goods(self): return self._call("clear_active_goods")
    def _clear_active_goods_direct(self): self._active_goods_id=None; return self._stop_explain_cycle(reason="clear_active_goods")
    def _pump_active_popup(self):
        if self._stop_event.is_set(): return None
        goods_id=self._active_goods_id
        if not goods_id: return None
        now=time.monotonic()
        if not self._popup_pending and now-self._last_popup_at<=self._popup_interval_sec:
            return None
        self._popup_pending=False
        try:
            self._do_popup(goods_id)
            self._last_popup_at=time.monotonic()
        except Exception as error:
            # The packaged worker advances the cooldown even on failure.  This
            # prevents a broken browser target from becoming a busy retry loop.
            self._last_popup_at=time.monotonic()
            print(f"[taobao.control] popup goods={goods_id} failed: {error}")
            if self._is_closed_target_error(str(error)):
                self._active_goods_id=None
                self._popup_pending=False
                self._do_recycle_page()
                time.sleep(.2)
        return None

    def _find_goods_item(self,page,target_id,max_retries=10):
        if page is None or page.is_closed(): return None
        target_id=int(target_id)
        for attempt in range(max(1,int(max_retries))):
            items=page.locator(".tcp-commodity-item")
            for index in range(items.count()):
                item=items.nth(index)
                if self._read_goods_id(item)==target_id:return item
            if attempt+1<max_retries:
                try: page.mouse.wheel(0,700); page.wait_for_timeout(250)
                except Exception: break
        return None
    @staticmethod
    def _item_raw_text(item):
        try: return str(item.inner_text() or "")
        except Exception: return ""
    @staticmethod
    def _read_goods_id(item):
        text=TaobaoLiveControl._item_raw_text(item)
        match=re.search(r"ID[:：\s]*(\d{5,})",text,re.I) or re.search(r"\b(\d{5,})\b",text)
        return int(match.group(1)) if match else None
    @staticmethod
    def _button_text(button):
        try: return str(button.inner_text() or "").strip()
        except Exception: return ""
    def _goods_is_explaining(self,page,goods_id):
        item=self._find_goods_item(page,goods_id,1)
        return bool(item and any(word in self._item_raw_text(item) for word in ("讲解中","取消讲解","结束讲解")))
    def _goods_is_occupied(self,page,goods_id):
        item=self._find_goods_item(page,goods_id,1)
        return bool(item and any(word in self._item_raw_text(item) for word in ("其他主播讲解","正在讲解")) and not self._goods_is_explaining(page,goods_id))
    def _other_goods_explaining(self,page,goods_id):
        if page is None or page.is_closed(): return False
        items=page.locator(".tcp-commodity-item")
        return any(self._read_goods_id(items.nth(i))!=int(goods_id) and any(word in self._item_raw_text(items.nth(i)) for word in ("讲解中","取消讲解","结束讲解")) for i in range(items.count()))
    def _click_explain_button(self,page,button):
        if page is None or page.is_closed() or button is None:return None
        button.click(timeout=15000)
    def _end_other_explaining(self,page,goods_id):
        if page is None or page.is_closed(): return False
        changed=False;items=page.locator(".tcp-commodity-item")
        for index in range(items.count()):
            item=items.nth(index)
            if self._read_goods_id(item)==int(goods_id) or not any(word in self._item_raw_text(item) for word in ("讲解中","取消讲解","结束讲解")): continue
            buttons=item.locator("button")
            for i in range(buttons.count()):
                if any(word in self._button_text(buttons.nth(i)) for word in ("结束","取消")):
                    buttons.nth(i).click(timeout=10000);changed=True;break
        return changed
    def _confirm_switch_explain(self,page):
        for text in ("确认切换","确认","继续"):
            locator=page.get_by_text(text,exact=True)
            if locator.count() and locator.first.is_visible(): locator.first.click(timeout=5000); return True
        return False
    def _dismiss_explain_dialogs(self,page,*,retries=1):
        changed=False
        for _ in range(max(1,int(retries))):
            for text in ("我知道了","知道了","关闭","取消"):
                locator=page.get_by_text(text,exact=True)
                if locator.count() and locator.first.is_visible():
                    try: locator.first.click(timeout=2000);changed=True
                    except Exception: pass
        return changed
    @classmethod
    def _resolve_explain_action(cls,item):
        if item is None:return "missing",None
        raw=cls._item_raw_text(item)
        if any(word in raw for word in ("讲解中","取消讲解","结束讲解")):return "already",None
        if any(word in raw for word in ("其他主播讲解","正在讲解")):return "occupied",None
        buttons=item.locator("button")
        for index in range(buttons.count()):
            button=buttons.nth(index);text=cls._button_text(button)
            if any(word in text for word in ("讲解","上讲解","开始")) and not any(word in text for word in ("结束","取消")):
                return "start",button
        return "missing",None
    def _start_explain_once(self,page,goods_id):
        item=self._find_goods_item(page,goods_id);action,button=self._resolve_explain_action(item)
        if action=="already":return True,False
        if action!="start":return False,action in {"missing","occupied"}
        if self._other_goods_explaining(page,goods_id):self._end_other_explaining(page,goods_id)
        if button is None:return False,True
        self._click_explain_button(page,button);self._confirm_switch_explain(page)
        return True,False
    def _do_popup(self,goods_id):
        if not self.connected() or not self.open_control_page(self._live_id): return False
        self._dismiss_explain_dialogs(self._page);result,_=self._start_explain_once(self._page,goods_id);return result
    def _stop_explain_cycle(self,*,reason):
        self._active_goods_id = None
        self._popup_pending = False
        self._explain_watch_until = 0.0
        self._explain_fail_streak = 0
        self._control_recover_streak = 0
        if reason:
            print(f"[taobao.control] stop explain cycle reason={reason}")
        return None
    def _arm_explain_watch(self,sec=_EXPLAIN_WATCH_SEC):
        deadline = time.monotonic() + max(1.0, float(sec))
        if deadline > self._explain_watch_until:
            self._explain_watch_until = deadline
        return None
    def _do_connect(self,*,headless=False): return self.connect(headless=headless)
    def _safe_close_browser(self):
        try: self.close()
        except Exception: pass
    def _page_current_url(self):
        try: return str(self._page.url or "")
        except Exception: return ""
    @staticmethod
    def _is_closed_target_error(msg):
        value=str(msg).lower(); return any(x in value for x in ("target closed","has been closed","browser has been closed","context or browser has been closed"))
    def _ensure_on_control_page(self,*,reason):
        if not self._playwright or not self._context or not self._page or self._stop_event.is_set():
            return False
        current_url=self._page_current_url()
        if _is_control_url(current_url,str(self._live_id or "")):
            self._control_recover_streak=0
            return True
        return self._recover_control_page(reason=reason)
    def _recover_control_page(self,*,reason):
        if self._stop_event.is_set() or not self._context:
            return False
        now=time.monotonic()
        if now<self._control_recover_at:
            return False
        self._control_recover_streak+=1
        delay=(_CONTROL_RECOVER_SLOW_SEC if self._control_recover_streak>=_CONTROL_RECOVER_MAX_STREAK
               else _CONTROL_RECOVER_COOLDOWN_SEC)
        self._control_recover_at=now+delay
        print(f"[taobao.control] recover control page reason={reason} streak={self._control_recover_streak}")
        old_page=self._page
        try:
            if old_page is None or old_page.is_closed():
                self._page=self._context.new_page()
            if not self.open_control_page(self._live_id):
                return False
            self._settle_control_page(self._page)
            self._dismiss_guides(self._page)
            self._close_stray_pages()
            self._control_recover_streak=0
            self._control_recover_at=0.0
            self._page_ready_at=time.monotonic()
            return True
        except Exception as error:
            print(f"[taobao.control] recover control page failed reason={reason}: {error}")
            if self._is_closed_target_error(str(error)):
                self._page=None
            return False
    def _settle_control_page(self,page,*,comment_wait_ms=15000):
        if page is None or page.is_closed(): return None
        try:
            page.wait_for_selector(GOODS_ITEM_SELECTOR,timeout=180000)
        except Exception:
            pass
        self._dismiss_guides(page)
        self._dismiss_explain_dialogs(page,retries=2)
        if int(comment_wait_ms)>0:
            try: page.wait_for_selector("#comment-page",timeout=int(comment_wait_ms))
            except Exception: pass
        return None
    def _close_stray_pages(self):
        if not self._context: return
        for page in list(self._context.pages):
            if page is not self._page:
                try: page.close()
                except Exception: pass
    @staticmethod
    def _dismiss_guides(page):
        if page is None or page.is_closed(): return
        for text in ("我知道了","跳过","下一步","关闭"):
            locator=page.get_by_text(text,exact=True)
            if locator.count() and locator.first.is_visible():
                try: locator.first.click(timeout=1000)
                except Exception: pass
    def _do_recycle_page(self):
        if not self._context:
            return None
        page=self._page
        try:
            if page is not None and not page.is_closed():page.close()
        except Exception:
            pass
        self._page=None
        recovered=self._recover_control_page(reason="recycle")
        self._explain_watch_until=0.0
        if recovered and self._active_goods_id:
            self._popup_pending=True
        return None
    def _pump_control_stay(self):
        if self._stop_event.is_set() or not self._playwright or not self._context:
            return None
        if self._is_page_alive():
            self._ensure_on_control_page(reason="control-stay")
        return None
    def _pump_explain_confirm(self): return self._confirm_switch_explain(self._page)
    def _pump_page_recycle(self):
        if self._stop_event.is_set() or not self._playwright or not self._context:
            return None
        if not self._is_page_alive() or self._page_ready_at<=0:
            return None
        if time.monotonic()-self._page_ready_at<_PAGE_RECYCLE_INTERVAL_SEC:
            return None
        self._do_recycle_page()
        return None
    def _worker_loop(self):
        while not self._stop_event.is_set():
            try: request=self._actions.get(timeout=.2)
            except Empty: request=None
            if request is not None:
                try: request["result"]=self._handle_action(request["action"],request.get("payload") or {})
                except BaseException as error: request["error"]=error
                finally:
                    if request.get("done") is not None: request["done"].set()
            if self.connected():
                for pump in (self._pump_control_stay,self._pump_explain_confirm,
                             self._pump_active_popup,self._pump_page_recycle):
                    try:pump()
                    except Exception:pass
        self._safe_close_browser()

    def _ensure_comment_panel(self, page, *, wait_timeout_ms=15000):
        panel = page.locator("#comment-page")
        if not panel.is_visible():
            page.get_by_text("评论", exact=True).first.click(timeout=wait_timeout_ms)
            panel.wait_for(state="visible", timeout=wait_timeout_ms)

    def _scrape_commodity_dom(self):
        return _scrape_commodity_dom(self._page)

    def _scrape_live_id(self):
        return _scrape_unpublished_live_id(self._page)

    def open_control_page(self, live_id=None):
        if not self._on_worker():
            return self._call("open_control_page", live_id=live_id)
        current_url = self._page.url
        if _is_control_url(current_url, "" if live_id is None else str(live_id)):
            self._live_id = parse_qs(urlsplit(current_url).query).get("liveId", [None])[0]
            return True
        if live_id is None:
            self._goto_live_page("https://liveplatform.taobao.com/restful/index/live/list")
            live_id = self._scrape_live_id()
        else:
            live_id = str(live_id)
        if not live_id or not live_id.isascii() or not live_id.isdecimal():
            return False
        url = f"https://liveplatform.taobao.com/restful/index/live/control?liveId={live_id}"
        self._goto_live_page(url)
        if not _is_control_url(self._page.url, live_id):
            return False
        self._live_id = live_id
        return True


    def _goto_live_page(self, url):
        self._page.goto(url)
        if urlsplit(self._page.url).hostname == "login.taobao.com":
            raise TaobaoLoginRequired("淘宝登录已失效，请重新登录")


def _fetch_taobao_commodity_products(*, headless=False, runtime_dir=None, storage_state=None):
    from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

    controller = TaobaoLiveControl._create(runtime_dir=runtime_dir)
    network_items = []

    def on_response(response):
        try:
            items = _favorite_response_items(response)
        except (ValueError, PlaywrightError):
            return
        if items is not None:
            network_items.extend(
                product
                for index, item in enumerate(items, 1)
                if (product := _normalize_product_item(item, index)) is not None
            )

    def work():
        try:
            controller._connect_configured(headless=headless, storage_state=storage_state)
            controller._page.on("response", on_response)
            controller._goto_live_page("https://liveplatform.taobao.com/restful/index/cargo/commodity/favorite")
            if network_items: return network_items
            try: controller._page.locator(".tcp-commodity-item").first.wait_for(state="attached", timeout=15000)
            except PlaywrightTimeoutError:
                if urlsplit(controller._page.url).hostname == "login.taobao.com": raise TaobaoLoginRequired("淘宝登录已失效，请重新登录")
            return network_items or controller._scrape_commodity_dom()
        finally: controller.close()
    try: return controller._call("_invoke",callback=work)
    finally: controller.shutdown()

def fetch_taobao_live_plan_products(*,headless=False):
    return _fetch_taobao_live_plan_products(headless=headless,runtime_dir=Path.cwd())

def fetch_taobao_commodity_products(*,headless=False):
    return _fetch_taobao_commodity_products(headless=headless,runtime_dir=Path.cwd())


def _fetch_taobao_live_plan_products(*, headless=False, runtime_dir=None, storage_state=None):
    """Fetch products attached to the newest not-yet-started live plan."""
    from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

    controller=TaobaoLiveControl._create(runtime_dir=runtime_dir)
    lives=[];products=[]

    def on_response(response):
        try:
            url=str(response.url or "")
            payload=_mtop_payload(response)
            if "mtop.taobao.dreamweb.live.list.query" in url:
                lives.extend(_parse_live_item_list(payload))
            elif "live.item" in url or "favorites.item.query" in url:
                raw=_parse_live_item_list(payload)
                for index,item in enumerate(raw,1):
                    normalized=_normalize_product_item(item,index)
                    if normalized is not None:products.append(normalized)
        except (ValueError,TypeError,PlaywrightError):
            return

    def work():
        controller._connect_configured(headless=headless,storage_state=storage_state)
        page=controller._page;page.on("response",on_response)
        controller._goto_live_page("https://liveplatform.taobao.com/restful/index/live/list")
        try:page.wait_for_selector("div.tblalm-lm-content",timeout=15000)
        except PlaywrightTimeoutError:
            if urlsplit(page.url).hostname=="login.taobao.com":raise TaobaoLoginRequired("淘宝登录已失效，请重新登录")
        _dismiss_live_plan_overlays(page)
        selected=_pick_latest_unpublished_live(lives)
        live_id=str((selected or {}).get("liveId") or (selected or {}).get("live_id") or (selected or {}).get("id") or "").strip()
        if not live_id:
            live_id=controller._scrape_live_id()
        if not live_id:return []
        controller._goto_live_page(f"https://liveplatform.taobao.com/restful/index/home/live/edit/v2?liveId={live_id}")
        _dismiss_live_plan_overlays(page)
        try:page.locator("#livePushed-tcl-unique-scroll-list .list-item").first.wait_for(state="attached",timeout=15000)
        except PlaywrightTimeoutError:pass
        if products:return products
        raw=page.evaluate("""() => Array.from(document.querySelectorAll('#livePushed-tcl-unique-scroll-list .list-item')).map((el, idx) => {
          const text=(el.innerText||'').replace(/\\s+/g,' ').trim();
          const id=(text.match(/(?:ID[:：\\s]*)?(\\d{5,})/)||[])[1]||'';
          const img=el.querySelector('img'); let src=(img&&(img.src||img.getAttribute('data-src')))||'';
          return {itemId:id,itemName:text,itemPic:src,itemUrl:id?('https://item.taobao.com/item.htm?id='+id):'',goodsIndex:idx+1};
        })""") or []
        return [item for index,value in enumerate(raw,1) if (item:=_normalize_product_item(value,index)) is not None]

    try:return controller._call("_invoke",callback=work)
    finally:controller.shutdown()

_controller = None
_controller_lock = RLock()
def get_taobao_controller():
    global _controller
    with _controller_lock:
        if _controller is None: _controller=TaobaoLiveControl._create(runtime_dir=Path.cwd())
        return _controller
def shutdown_taobao_controller():
    global _controller
    with _controller_lock: controller,_controller=_controller,None
    if controller is not None: controller.shutdown()

def login_taobao_account(*,force_relogin=False,headless=False,login_timeout_sec=600):
    controller=get_taobao_controller()
    try:
        storage=taobao_storage_path(Path.cwd())
        controller.login(storage_path=storage,login_timeout_sec=login_timeout_sec,force_relogin=force_relogin)
        status=_get_taobao_account_status(Path.cwd(),storage)
        return {"status":"success",**status}
    except Exception as error:
        return {"status":"error","message":str(error)}


def _probe_taobao_live_status(*, headless=False, login_timeout_sec=600, runtime_dir=None, storage_state=None):
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    controller = TaobaoLiveControl._create(runtime_dir=runtime_dir)
    def work():
        controller._connect_configured(headless=headless, storage_state=storage_state); target="https://liveplatform.taobao.com/restful/index/live/list"
        try: controller._goto_live_page(target); live_id=controller._scrape_live_id()
        except TaobaoLoginRequired:
            if headless or (runtime_dir is None and not isinstance(storage_state,(str,Path))): raise
            storage_path=storage_state if isinstance(storage_state,(str,Path)) else None
            controller.login(storage_path=storage_path,login_timeout_sec=login_timeout_sec); controller._goto_live_page(target); live_id=controller._scrape_live_id()
        return {"status":"success","live_id":live_id}
    try:
        return controller._call("_invoke",timeout=float(login_timeout_sec)+60,callback=work)
    except TaobaoLoginRequired as error:
        return {"status": "error", "message": str(error)}
    except PlaywrightTimeoutError:
        return {"status": "error", "message": "等待淘宝页面或登录超时"}
    finally: controller.shutdown()

def probe_taobao_live_status(*,headless=False,login_timeout_sec=600):
    return _probe_taobao_live_status(headless=headless,login_timeout_sec=login_timeout_sec,runtime_dir=Path.cwd())
