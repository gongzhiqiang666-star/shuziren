"""Recovered Shopee Live seller-centre control integration."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Event, RLock, Thread, current_thread
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

_CHROME_DEBUG_PORT = 9223
_DEFAULT_POPUP_INTERVAL_SEC = 12.0
_MIN_POPUP_INTERVAL_SEC = 5.0
_DEFAULT_ENTER_LIVE_TIMEOUT_SEC = 60.0
_DEFAULT_PRODUCTS_WAIT_SEC = 30.0
_AUTH_COOKIE_NAMES = {"SPC_EC", "SPC_ST", "SPC_U", "SPC_SI"}
_LS_PRODUCTS_PREFIX = "shopee-live-streaming-STORAGE_PRODUCTS_"
_LS_SESSION = "shopee-live-streaming-STORAGE_SESSION"
COMMENT_MAX_LEN = 200
SELLER_SHOP_NAME_SELECTOR = ".account-info .subaccount-name"
LIVE_CONTROL_READY_SELECTOR = ".divTextarea_12bb8, [contenteditable=true], .contentText_e9ad8, [class*='contentText']"
DEFAULT_ACCOUNTS_ORIGIN = "https://accounts.shopee.com.my"
DEFAULT_SELLER_ORIGIN = "https://seller.shopee.com.my"
SELLER_HOME_URL = DEFAULT_SELLER_ORIGIN
LIVE_CONTROL_URL = "https://live.shopee.com.my/pc/sessionList"
_chrome_lock = RLock()
_chrome_proc = None

_LOGIN_URL_RE = re.compile(
    r".*(?:accounts\.shopee\.[^/]+/seller/login|seller\.shopee\.[^/]+/"
    r"(?:buyer/login|account/signin)|(?:www\.)?shopee\.[^/]+/"
    r"(?:buyer/login|live/login)|login\.shopee|verify/captcha).*",
    re.I,
)

_LOGIN_CHALLENGE_JS = r"""() => {
  const t = (document.body && document.body.innerText) || '';
  return /Please slide to complete|Verify to Continue/i.test(t);
}"""

_LIVE_WORKSPACE_JS = r"""() => {
  const t = (document.body && document.body.innerText) || '';
  if (/Please slide to complete|Verify to Continue/i.test(t)) return false;
  if (document.querySelector('.divTextarea_12bb8, [contenteditable=true]')) return true;
  if (/Shop Name:\s/i.test(t)) return true;
  if (/\bEnd Live\b/i.test(t)) return true;
  const tiles = Array.from(document.querySelectorAll('.contentText_e9ad8, [class*="contentText"]'));
  return tiles.some((el) => ((el.innerText || '').trim()) === 'Products');
}"""

_LIVING_JS = r"""() => {
  const t = (document.body && document.body.innerText) || '';
  if (/End Live/i.test(t) && /Shop Name:/i.test(t)) return true;
  return !!document.querySelector('.divTextarea_12bb8, [contenteditable=true]');
}"""

_SCRAPE_SHOP_NAME_JS = r"""() => {
  const el = document.querySelector('.account-info .subaccount-name');
  const direct = ((el && el.innerText) || '').trim();
  if (direct) return direct;
  const text = (document.body && document.body.innerText) || '';
  const m = text.match(/Shop Name:\s*\n?\s*([^\n]+)/i);
  if (m && m[1]) return m[1].trim();
  try {
    const raw = localStorage.getItem('@shopee/account-basic-info');
    if (raw) {
      const obj = JSON.parse(raw);
      const name = obj.shop_name || obj.shopName || obj.nickname || obj.username || '';
      if (name) return String(name).trim();
    }
  } catch (e) {}
  return '';
}"""

_READ_COMMENTS_JS = r"""() => {
  const roots = Array.from(document.querySelectorAll('.comment-content_c709a .ReactVirtualized__Grid__innerScrollContainer > div, .comment-content_c709a [data-comment-id]'));
  const seen = new Set(), rows = [];
  for (const el of roots) {
    const contentEl = el.querySelector('.message-content_3bb92');
    const content = ((contentEl && contentEl.innerText) || '').replace(/\s+/g, ' ').trim();
    if (!content) continue;
    const nickEl = el.querySelector('.user-name_2fad3');
    const nickname = ((nickEl && nickEl.innerText) || '').replace(/\s+/g, ' ').trim();
    const isHost = !!el.querySelector('.host-item_32da9, .host-icon_3f8fa');
    const isNotice = !!el.querySelector('.announce-icon_d01bb, .seller-icon-notice');
    const uid = el.getAttribute('data-uid') || '';
    const commentId = el.getAttribute('data-comment-id') || '';
    const key = [commentId, uid, nickname, content].join('|');
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({nickname, tag: isHost ? 'Host' : (isNotice ? 'Notice' : ''), time: '', content, uid, commentId});
  }
  return rows;
}"""

_FILL_COMMENT_JS = r"""(text) => {
  document.querySelectorAll('.shopee-react-modal__close').forEach((el) => { try { el.click(); } catch (e) {} });
  const el = document.querySelector('.divTextarea_12bb8, [contenteditable=true]');
  if (!el) return {ok:false, reason:'no textarea'};
  el.focus(); el.textContent = text;
  el.dispatchEvent(new InputEvent('input', {bubbles:true, data:text, inputType:'insertText'}));
  return {ok:true, value:(el.innerText || '').trim(), len:(el.innerText || '').trim().length};
}"""

_CLICK_SHOW_GOODS_JS = r"""(goodsId) => {
  const want = String(goodsId), rows = Array.from(document.querySelectorAll('tr'));
  for (const tr of rows) {
    const text = ((tr.innerText || '').replace(/\s+/g, ' ') || '').trim();
    const idMatch = text.match(/^(\d+)\b/);
    if (!idMatch || idMatch[1] !== want) continue;
    if (/\bShowing\b/i.test(text)) return {ok:true, already:true, row:text.slice(0,160)};
    const btn = Array.from(tr.querySelectorAll('button')).find((b) => /^Show$/i.test((b.innerText || '').trim()) && !b.disabled && b.offsetParent !== null);
    if (!btn) return {ok:false, reason:'row found but no Show', row:text.slice(0,160)};
    btn.click(); return {ok:true, row:text.slice(0,160)};
  }
  return {ok:false, reason:`goods ${want} row not found`, rows:rows.length};
}"""

_SCRAPE_PRODUCTS_JS = r"""() => Array.from(document.querySelectorAll('tr')).map((tr) => {
  const text = ((tr.innerText || '').replace(/\s+/g, ' ') || '').trim();
  const idMatch = text.match(/^(\d+)\b/), priceMatch = text.match(/RM\s*([0-9]+(?:\.[0-9]+)?)/i);
  const name = text.replace(/^\d+\s*/, '').replace(/RM[\d\.\s~].*$/i, '').replace(/\b(Show|Showing|Move to Top|Remove|Comm Rate.*)$/i, '').trim();
  return {id:idMatch ? Number(idMatch[1]) : 0, name, price:priceMatch ? priceMatch[1] : '', text:text.slice(0,240)};
}).filter((x) => x.id > 0 && x.name)"""

_READ_PRODUCTS_STORAGE_JS = r"""(sid) => {
  const prefix = 'shopee-live-streaming-STORAGE_PRODUCTS_';
  const candidates = sid ? [prefix + sid] : Object.keys(localStorage).filter((key) => key.startsWith(prefix));
  for (const key of candidates) {
    try {
      const value = JSON.parse(localStorage.getItem(key) || 'null');
      const rows = Array.isArray(value) ? value : (value && (value.products || value.items || value.data));
      if (Array.isArray(rows) && rows.length) return rows;
    } catch (e) {}
  }
  return [];
}"""

_PRODUCTS_PANEL_READY_JS = r"""() => Array.from(document.querySelectorAll('tr')).some((tr) => {
  const text = tr.innerText || '';
  return /\bShow\b|\bShowing\b/i.test(text);
})"""

_OPEN_PRODUCTS_PANEL_JS = r"""() => {
  document.querySelectorAll('.shopee-react-modal__close').forEach((el) => { try { el.click(); } catch (e) {} });
  const prefer = Array.from(document.querySelectorAll('.contentText_e9ad8, [class*="contentText"]'))
    .find((el) => ((el.innerText || '').trim()) === 'Products' && el.offsetParent !== null);
  if (prefer) {
    const target = prefer.closest('.content_3d860, [class*="content_"], [class*="tool"], button, div') || prefer;
    target.click(); return {ok:true, via:'contentText'};
  }
  const hit = Array.from(document.querySelectorAll('div,span,button,a')).find((el) => {
    const own = Array.from(el.childNodes).filter((n) => n.nodeType === 3)
      .map((n) => (n.textContent || '').trim()).join('');
    const text = (own || (el.innerText || '').trim().split('\n')[0] || '').trim();
    return text === 'Products' && el.offsetParent !== null;
  });
  if (!hit) return {ok:false, reason:'Products tile not found'};
  hit.click(); return {ok:true, via:'text'};
}"""


def _client_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "yunchuang_v122" / "_internal"
        if candidate.is_dir():
            return candidate
        if (parent / "tools").is_dir() and (parent / "assets").is_dir():
            return parent
    return here.parent.parent


def get_storage_path() -> Path:
    return _client_root() / "tools" / "auto_live_action" / "user_data" / "shopee_storage.json"


def clear_shopee_storage() -> None:
    path = get_storage_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _read_storage_payload() -> Dict[str, Any]:
    try:
        payload = json.loads(get_storage_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _cookies_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    state = payload.get("storage_state") if isinstance(payload, dict) else None
    source = state if isinstance(state, dict) else payload
    cookies = source.get("cookies", []) if isinstance(source, dict) else []
    return [cookie for cookie in cookies if isinstance(cookie, dict)]


def _cookie_value(cookies: List[Dict[str, Any]], name: str) -> str:
    return next((str(cookie.get("value") or "") for cookie in cookies if cookie.get("name") == name), "")


def _read_user_id_from_storage() -> str:
    payload = _read_storage_payload()
    return str(payload.get("user_id") or _cookie_value(_cookies_from_payload(payload), "SPC_U") or "").strip()


def _read_shop_name_from_storage() -> str:
    return str(_read_storage_payload().get("shop_name") or "").strip()


def _read_session_id_from_storage() -> str:
    return str(_read_storage_payload().get("session_id") or "").strip()


def _has_auth_cookies(cookies: List[Dict[str, Any]]) -> bool:
    names = {str(cookie.get("name") or "") for cookie in cookies}
    return bool(names & _AUTH_COOKIE_NAMES)


def get_shopee_account_status() -> Dict[str, Any]:
    payload = _read_storage_payload()
    cookies = _cookies_from_payload(payload)
    return {
        "has_storage": bool(payload),
        "logged_in": _has_auth_cookies(cookies),
        "shop_name": str(payload.get("shop_name") or "").strip(),
        "user_id": str(payload.get("user_id") or _cookie_value(cookies, "SPC_U") or "").strip(),
        "session_id": str(payload.get("session_id") or "").strip(),
    }


def _normalize_product_item(raw: Dict[str, Any], fallback_index: int) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    item_id = raw.get("itemId") or raw.get("item_id") or raw.get("goods_id") or raw.get("id")
    item_id = str(item_id or "").strip()
    if not item_id or not item_id.isdigit():
        return None
    name = str(raw.get("itemName") or raw.get("item_name") or raw.get("name") or raw.get("title") or "").strip()
    price = raw.get("itemPrice", raw.get("item_price", raw.get("price", raw.get("minPrice", ""))))
    image = str(raw.get("itemPic") or raw.get("item_pic") or raw.get("image") or "").strip()
    if image.startswith("//"):
        image = "https:" + image
    index = raw.get("goodsIndex") or raw.get("goods_index") or fallback_index
    try:
        index = int(index)
    except (TypeError, ValueError, OverflowError):
        index = fallback_index
    url = str(raw.get("itemUrl") or raw.get("item_url") or "").strip()
    return {
        "itemId": item_id,
        "itemName": name,
        "itemPrice": "" if price is None else str(price).strip(),
        "itemPic": image,
        "itemUrl": url or f"https://shopee.com.my/product/0/{item_id}",
        "sellerId": str(raw.get("sellerId") or raw.get("seller_id") or "").strip(),
        "goodsIndex": index,
    }


def format_shopee_product_content(item: Dict[str, Any]) -> str:
    product = _normalize_product_item(item, 1)
    if product is None:
        return ""
    parts = [product["itemName"]]
    if product["itemPrice"]:
        parts.append(f"RM {product['itemPrice']}")
    return "\n".join(part for part in parts if part)


def _session_id_from_url(url: str) -> str:
    parsed = urlparse(url or "")
    values = parse_qs(parsed.query).get("session", [])
    return str(values[0]).strip() if values else ""


def _live_url(session_id: str) -> str:
    return f"https://live.shopee.com.my/pc/live?session={session_id}"


def _start_url() -> str:
    session_id = _read_session_id_from_storage()
    return _live_url(session_id) if session_id else LIVE_CONTROL_URL


def _chrome_debug_endpoint(port: int = _CHROME_DEBUG_PORT) -> str:
    return f"http://127.0.0.1:{int(port)}"


def _is_cdp_ready(port: int = _CHROME_DEBUG_PORT, timeout: float = 1.0) -> bool:
    try:
        with urlopen(_chrome_debug_endpoint(port) + "/json/version", timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def _wait_cdp_ready(port: int = _CHROME_DEBUG_PORT, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_cdp_ready(port):
            return True
        time.sleep(0.2)
    return False


def _resolve_chrome_path() -> str:
    candidates = [
        shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google/Chrome/Application/chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google/Chrome/Application/chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google/Chrome/Application/chrome.exe"),
    ]
    return next((path for path in candidates if path and Path(path).is_file()), "")


def _spawn_chrome_debug(port: int = _CHROME_DEBUG_PORT) -> subprocess.Popen:
    chrome = _resolve_chrome_path()
    if not chrome:
        raise FileNotFoundError("Google Chrome not found")
    profile = get_storage_path().parent / "shopee_chrome_profile"
    profile.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        [chrome, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--remote-allow-origins=*", "--no-first-run", "--no-default-browser-check",
         "--disable-popup-blocking", _start_url()],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags,
    )


def _ensure_chrome_running(port: int = _CHROME_DEBUG_PORT) -> None:
    global _chrome_proc
    with _chrome_lock:
        if _is_cdp_ready(port):
            return None
        if _chrome_proc is not None and _chrome_proc.poll() is not None:
            _chrome_proc=None
        if _chrome_proc is None:
            _chrome_proc=_spawn_chrome_debug(port)
        if not _wait_cdp_ready(port):
            _stop_chrome_debug(port)
            raise RuntimeError(f"Shopee Chrome debug port={port} 启动失败，请确认本机 Chrome 可启动后重试")
    return None


def _stop_chrome_debug(port: int = _CHROME_DEBUG_PORT) -> None:
    global _chrome_proc
    with _chrome_lock:
        process,_chrome_proc=_chrome_proc,None
    if process is None:return None
    try:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=5)
    except Exception as error:
        print(f"[shopee.control] stop Chrome debug port={port} failed: {error}")
    return None


def _connect_cdp(playwright, *, port: int = _CHROME_DEBUG_PORT, headless: bool = False):
    return playwright.chromium.connect_over_cdp(_chrome_debug_endpoint(port))


def _disconnect_cdp(browser) -> None:
    if browser is not None:
        browser.close()


def _maybe_hydrate_cookies_from_storage(context) -> None:
    """Import legacy storage JSON only when the Chrome profile has no auth cookie."""
    try:
        current=list(context.cookies() or [])
        if _has_auth_cookies(current):
            return
        saved=_cookies_from_payload(_read_storage_payload())
        if _has_auth_cookies(saved):
            context.add_cookies(saved)
    except Exception as error:
        print(f"[shopee.control] hydrate cookies failed: {error}")


def _merge_storage_meta(context, *, shop_name: Optional[str] = None, site: str = "my",
                        page_url: str = "", session_id: Optional[str] = None) -> None:
    payload=_read_storage_payload()
    try:
        payload["storage_state"]=context.storage_state()
    except Exception:
        payload.setdefault("storage_state",{"cookies":[],"origins":[]})
    cookies=_cookies_from_payload(payload)
    if shop_name is not None:payload["shop_name"]=str(shop_name).strip()
    if session_id is not None:payload["session_id"]=str(session_id).strip()
    payload["user_id"]=str(payload.get("user_id") or _cookie_value(cookies,"SPC_U") or "").strip()
    payload["site"]=str(site or "my")
    payload["page_url"]=str(page_url or "")
    payload["saved_at"]=time.strftime("%Y-%m-%dT%H:%M:%S")
    path=get_storage_path();path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(temporary,path)


def _cdp_context_and_page(browser, *, prefer_live: bool = False) -> Tuple[Any, Any]:
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    pages = list(context.pages)
    page = next((p for p in pages if prefer_live and "/pc/live" in p.url), None)
    page = page or next((p for p in pages if "shopee" in p.url and not p.url.startswith("chrome://")), None)
    return context, page or context.new_page()


def _mid_control_busy() -> bool:
    controller=globals().get("_controller")
    thread=getattr(controller,"_thread",None) if controller is not None else None
    return bool(thread is not None and thread.is_alive() and current_thread() is not thread)


def _read_session_id_from_page(page) -> str:
    return _session_id_from_url(page.url) or str(page.evaluate(f"() => localStorage.getItem('{_LS_SESSION}') || ''") or "").strip()


def _dismiss_modals(page) -> None:
    try:
        page.evaluate("""() => { document.querySelectorAll('.shopee-react-modal__close').forEach((el) => { try { el.click(); } catch (e) {} }); }""")
    except Exception:
        pass
    try:page.keyboard.press("Escape")
    except Exception:pass


def _page_is_login_surface(page) -> bool:
    try:
        url=str(page.url or "")
        if _LOGIN_URL_RE.match(url):
            return True
        locator=page.locator("input[name=loginKey], form input[type=password]")
        if locator.count() and locator.first.is_visible():
            return True
        return bool(page.evaluate(_LOGIN_CHALLENGE_JS))
    except Exception:
        return False


def _page_has_seller_centre(page) -> bool:
    try:
        return bool(page.locator(".account-info .subaccount-name, .account-info .account-avatar").count())
    except Exception:
        return False


def _page_has_live_workspace(page) -> bool:
    try:
        url=str(page.url or "")
        if "live.shopee" not in url or "/pc/live" not in url:
            return False
        return bool(page.locator(".divTextarea_12bb8, [contenteditable=true], .contentText_e9ad8, [class*='contentText']").count())
    except Exception:
        return False


def _page_looks_logged_in(page) -> bool:
    if _page_is_login_surface(page):
        return False
    if _page_has_seller_centre(page) or _page_has_live_workspace(page):
        return True
    try:
        return _has_auth_cookies(page.context.cookies())
    except Exception:
        return False


def _page_is_live_control(page) -> bool:
    try:
        url=str(page.url or "")
        if "live.shopee" not in url or "/pc/live" not in url or not _session_id_from_url(url):
            return False
        if _page_is_login_surface(page):
            return False
        return bool(page.evaluate(_LIVE_WORKSPACE_JS))
    except Exception:
        return False


def _page_looks_living(page) -> bool:
    if not _page_is_live_control(page):
        return False
    try:
        return bool(page.evaluate(_LIVING_JS))
    except Exception:
        return False


def _wait_until_logged_in(page, *, timeout_sec: float = 600) -> bool:
    deadline=time.monotonic()+max(0.0,float(timeout_sec))
    while time.monotonic()<deadline:
        _dismiss_modals(page)
        if _page_looks_logged_in(page):return True
        try:page.wait_for_timeout(250)
        except Exception:time.sleep(.25)
    return _page_looks_logged_in(page)


def _scrape_shop_name(page) -> str:
    try:return str(page.evaluate(_SCRAPE_SHOP_NAME_JS) or "").strip()
    except Exception:return ""


def _resolve_shop_name(page) -> str:
    return _scrape_shop_name(page) or _read_shop_name_from_storage()


def _scrape_products_from_dom(page) -> List[Dict[str, Any]]:
    raw_items = page.evaluate(_SCRAPE_PRODUCTS_JS) or []
    return [item for index, raw in enumerate(raw_items, 1) if (item := _normalize_product_item(raw, index))]


def _read_products_from_local_storage(page, sid: str = "") -> List[Dict[str, Any]]:
    try:raw_items=page.evaluate(_READ_PRODUCTS_STORAGE_JS,str(sid or "")) or []
    except Exception:return []
    return [item for index,raw in enumerate(raw_items,1)
            if (item:=_normalize_product_item(raw,index)) is not None]


def _collect_session_products(page, sid: str = "") -> List[Dict[str, Any]]:
    combined=[*_read_products_from_local_storage(page,sid),*_scrape_products_from_dom(page)]
    output=[];seen=set()
    for item in combined:
        item_id=item["itemId"]
        if item_id in seen:continue
        seen.add(item_id);output.append(item)
    for index,item in enumerate(output,1):item["goodsIndex"]=index
    return output


def _wait_until_live_control(page, *, timeout_sec: float = _DEFAULT_ENTER_LIVE_TIMEOUT_SEC) -> bool:
    deadline=time.monotonic()+max(0.0,float(timeout_sec))
    while time.monotonic()<deadline:
        _dismiss_modals(page)
        if _page_is_live_control(page):return True
        try:page.wait_for_timeout(250)
        except Exception:time.sleep(.25)
    return _page_is_live_control(page)


def _wait_until_products(page, *, sid: str = "", timeout_sec: float = _DEFAULT_PRODUCTS_WAIT_SEC) -> List[Dict[str, Any]]:
    deadline=time.monotonic()+max(0.0,float(timeout_sec))
    while time.monotonic()<deadline:
        products=_collect_session_products(page,sid)
        if products:return products
        try:page.wait_for_timeout(300)
        except Exception:time.sleep(.3)
    return _collect_session_products(page,sid)


def _products_panel_ready(page) -> bool:
    try:return bool(page.evaluate(_PRODUCTS_PANEL_READY_JS))
    except Exception:return False


def _open_products_panel(page) -> bool:
    _dismiss_modals(page)
    if _products_panel_ready(page):return True
    try:result=page.evaluate(_OPEN_PRODUCTS_PANEL_JS)
    except Exception:return False
    if not isinstance(result,dict) or not result.get("ok"):return False
    try:page.wait_for_timeout(300)
    except Exception:pass
    return _products_panel_ready(page)


def _restore_connected_page(page) -> Tuple[str, str]:
    """Restore the seller/live page selected by the persisted Shopee session.

    Login surfaces are deliberately left open so ``login_shopee_account`` can
    wait for interactive login.  Once authenticated, the packaged controller
    prefers an existing live session and otherwise returns to the session list.
    """
    if str(page.url or "") == "about:blank":
        page.goto(_start_url(), wait_until="domcontentloaded")
    if _page_is_login_surface(page):
        return "", ""
    if not _page_looks_logged_in(page):
        page.goto(SELLER_HOME_URL, wait_until="domcontentloaded")
        if _page_is_login_surface(page) or not _page_looks_logged_in(page):
            return "", ""
    shop_name = _resolve_shop_name(page)
    session_id = _read_session_id_from_page(page) or _read_session_id_from_storage()
    if session_id:
        if not _page_is_live_control(page):
            page.goto(_live_url(session_id), wait_until="domcontentloaded",
                      timeout=int(_DEFAULT_ENTER_LIVE_TIMEOUT_SEC * 1000))
            _wait_until_live_control(page, timeout_sec=_DEFAULT_ENTER_LIVE_TIMEOUT_SEC)
    elif not _page_has_live_workspace(page) and "/pc/sessionList" not in str(page.url or ""):
        page.goto(LIVE_CONTROL_URL, wait_until="domcontentloaded")
    return shop_name, session_id


def _click_show_goods(page, goods_id: int) -> Dict[str, Any]:
    result = page.evaluate(_CLICK_SHOW_GOODS_JS, int(goods_id))
    return result if isinstance(result, dict) else {"ok": False, "reason": "invalid result"}


class ShopeeLiveControl:
    def __init__(self) -> None:
        self._lock = RLock()
        self._playwright = self._browser = self._context = self._page = None
        self._chrome_proc = None
        self._connected = False
        self._initializing = False
        self._mid_control_busy = False
        self._session_id = ""
        self._active_goods_id: Optional[int] = None
        self._popup_interval_sec = _DEFAULT_POPUP_INTERVAL_SEC
        self._last_popup_at = 0.0
        self._popup_pending = False
        self._actions = Queue(); self._stop_event = Event(); self._thread = None

    def connected(self) -> bool:
        return self._connected and self._is_page_alive()

    def session_id(self) -> str:
        return self._session_id

    def ensure_worker(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive(): return self._thread
            self._stop_event.clear(); self._thread=Thread(target=self._worker_loop,name="shopee-live-control",daemon=True); self._thread.start(); return self._thread

    def _on_worker(self) -> bool:
        return self._thread is not None and current_thread() is self._thread

    def _call(self, action: str, timeout: float = 180.0, **payload: Any) -> Any:
        if self._on_worker(): return self._handle_action(action,payload)
        self.ensure_worker(); done=Event(); request={"action":action,"payload":payload,"done":done}; self._actions.put(request)
        if not done.wait(timeout): raise TimeoutError(f"Shopee action timed out: {action}")
        if request.get("error") is not None: raise request["error"]
        return request.get("result")

    def _post(self, action: str, **payload: Any) -> None:
        self.ensure_worker(); self._actions.put({"action":action,"payload":payload})

    def connect(self, *, headless: bool = False) -> bool:
        if not self._on_worker(): return bool(self._call("connect",headless=headless))
        return self._do_connect(headless=headless)

    def _do_connect(self, *, headless: bool = False) -> bool:
        with self._lock:
            if self.connected():
                return True
            self._safe_close_browser()
            self._initializing=True
            try:
                if self._playwright is None:
                    from playwright.sync_api import sync_playwright
                    self._playwright=sync_playwright().start()
                _ensure_chrome_running()
                self._chrome_proc=_chrome_proc
                self._browser = _connect_cdp(self._playwright,headless=headless)
                self._context, self._page = _cdp_context_and_page(self._browser, prefer_live=True)
                _maybe_hydrate_cookies_from_storage(self._context)
                shop_name, self._session_id = _restore_connected_page(self._page)
                self._initializing=False
                self._connected = True
                self._save_storage_state(shop_name=shop_name or None,
                                         session_id=self._session_id)
                return True
            except Exception as error:
                print(f"[shopee.control] connect failed: {error}")
                self._safe_close_browser()
                return False

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try: request=self._actions.get(timeout=.2)
            except Empty: request=None
            if request is not None:
                try: request["result"]=self._handle_action(request["action"],request.get("payload") or {})
                except BaseException as error: request["error"]=error
                finally:
                    if request.get("done") is not None: request["done"].set()
            if self.connected():
                try: self._pump_active_popup()
                except Exception: pass
        self._safe_close_browser()

    def ensure_connected(self, *, headless: bool = False) -> bool:
        return self.connected() or self.connect(headless=headless)

    def disconnect(self) -> None:
        if not self._on_worker(): return self._call("disconnect")
        with self._lock:
            self._safe_close_browser()

    def popup(self, goods_id: int) -> None:
        self._post("popup", goods_id=int(goods_id))

    def set_active_goods(self, goods_id: int, *, interval_sec: float = _DEFAULT_POPUP_INTERVAL_SEC) -> None:
        return self._call("set_active_goods",goods_id=int(goods_id),interval_sec=float(interval_sec))

    def clear_active_goods(self) -> None:
        return self._call("clear_active_goods")

    def fetch_comments(self) -> List[Dict[str, str]]:
        return self._call("fetch_comments")

    def send_comment(self, text: str) -> bool:
        if not isinstance(text, str) or not text.strip():
            return False
        return bool(self._call("send_comment", text=text.strip()[:COMMENT_MAX_LEN]))

    def shutdown(self) -> None:
        try:
            self.disconnect()
        except Exception as error:
            print(f"[shopee.control] shutdown disconnect failed: {error}")
        finally:
            self._stop_event.set(); self._actions.put(None)
            thread=self._thread
            if thread and thread.is_alive() and thread is not current_thread(): thread.join(timeout=5)
            self._thread=None

    def _handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        if action == "connect": return self._do_connect(headless=bool(payload.get("headless")))
        if action == "disconnect":
            self._active_goods_id=None
            self._popup_pending=False
            self._safe_close_browser()
            self._connected=False
            return True
        if action == "fetch_comments": return self._do_fetch_comments()
        if action == "send_comment": return self._do_send_comment(str(payload.get("text") or ""))
        if action == "popup": return self._do_popup(int(payload["goods_id"]))
        if action == "set_active_goods":
            interval=payload.get("interval_sec") or _DEFAULT_POPUP_INTERVAL_SEC
            self._popup_interval_sec=max(_MIN_POPUP_INTERVAL_SEC,float(interval))
            self._active_goods_id=int(payload["goods_id"])
            self._popup_pending=True
            return True
        if action == "clear_active_goods":
            self._active_goods_id=None
            self._popup_pending=False
            return True
        if action == "_invoke": return payload["callback"]()
        raise ValueError(f"unknown Shopee action: {action}")

    def _pump_active_popup(self) -> None:
        goods_id=self._active_goods_id
        if goods_id is None or not self._connected or self._page is None:
            return
        now = time.monotonic()
        if not self._popup_pending and now-self._last_popup_at<=self._popup_interval_sec:
            return
        self._popup_pending=False
        try:
            self._do_popup(goods_id)
            self._last_popup_at=time.monotonic()
        except Exception as error:
            self._last_popup_at=time.monotonic()
            print(f"[shopee.control] popup goods={goods_id} failed: {error}")
            if self._is_closed_target_error(str(error)):
                self._active_goods_id=None
                self._popup_pending=False
                self._safe_close_browser()

    def _is_page_alive(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    @staticmethod
    def _is_closed_target_error(msg: str) -> bool:
        lowered = str(msg).lower()
        return any(text in lowered for text in ("target closed", "has been closed", "browser has been closed", "context or browser has been closed"))

    def _do_fetch_comments(self) -> List[Dict[str, str]]:
        if not self.ensure_connected():
            return []
        return list(self._page.evaluate(_READ_COMMENTS_JS) or [])

    def _do_send_comment(self, text: str) -> bool:
        if not self.ensure_connected() or not text:
            return False
        result = self._page.evaluate(_FILL_COMMENT_JS, text)
        if not isinstance(result, dict) or not result.get("ok"):
            return False
        return bool(self._page.evaluate("() => { const b=[...document.querySelectorAll('button')].find(x=>/^Send$/i.test((x.innerText||'').trim())); if(!b)return false; b.click(); return true; }"))

    def _do_popup(self, goods_id: int) -> bool:
        if not self.ensure_connected():
            return False
        return bool(_click_show_goods(self._page, goods_id).get("ok"))

    def _save_storage_state(self, *, shop_name: Optional[str] = None, session_id: Optional[str] = None) -> None:
        if self._context is None:return None
        _merge_storage_meta(self._context,shop_name=shop_name,page_url=self._page.url if self._page else "",session_id=session_id)

    def _safe_close_browser(self) -> None:
        self._connected=False
        self._session_id=""
        self._initializing=False
        browser,self._browser=self._browser,None
        self._context=None
        self._page=None
        _disconnect_cdp(browser)


_controller_lock = RLock()
_controller: Optional[ShopeeLiveControl] = None


def get_shopee_controller() -> ShopeeLiveControl:
    global _controller
    with _controller_lock:
        if _controller is None:
            _controller = ShopeeLiveControl()
        return _controller


def login_shopee_account(*, force_relogin: bool = False, headless: bool = False, login_timeout_sec: float = 600) -> Dict[str, Any]:
    if force_relogin:
        clear_shopee_storage()
    controller = get_shopee_controller()
    def work():
        controller.ensure_connected(headless=headless)
        deadline = time.monotonic() + login_timeout_sec
        while time.monotonic() < deadline:
            cookies = controller._context.cookies()
            if _has_auth_cookies(cookies) and not _LOGIN_URL_RE.match(controller._page.url):
                controller._session_id = _read_session_id_from_page(controller._page)
                controller._save_storage_state(session_id=controller._session_id)
                return {"status": "success", **get_shopee_account_status()}
            controller._page.wait_for_timeout(500)
        return {"status": "error", "message": "等待 Shopee 登录超时"}
    try:
        return controller._call("_invoke",timeout=float(login_timeout_sec)+30,callback=work)
    except Exception as error:
        return {"status": "error", "message": str(error)}


def fetch_shopee_session_products(*, headless: bool = False, enter_timeout_sec: float = _DEFAULT_ENTER_LIVE_TIMEOUT_SEC, products_timeout_sec: float = _DEFAULT_PRODUCTS_WAIT_SEC) -> List[Dict[str, Any]]:
    controller = get_shopee_controller()
    def work():
        controller.ensure_connected(headless=headless)
        if controller._session_id and "/pc/live" not in controller._page.url: controller._page.goto(_live_url(controller._session_id),wait_until="domcontentloaded",timeout=int(enter_timeout_sec*1000))
        if not _wait_until_live_control(controller._page,timeout_sec=enter_timeout_sec):return []
        _open_products_panel(controller._page)
        return _wait_until_products(controller._page,sid=controller._session_id,timeout_sec=products_timeout_sec)
    return controller._call("_invoke",timeout=float(enter_timeout_sec+products_timeout_sec)+30,callback=work)


def probe_shopee_live_status(*, headless: bool = False, login_timeout_sec: float = 600) -> Dict[str, Any]:
    controller = get_shopee_controller()
    def work():
        controller.ensure_connected(headless=headless); session_id=_read_session_id_from_page(controller._page); living=bool(session_id and "/pc/live" in controller._page.url)
        return {"status":"success","logged_in":not bool(_LOGIN_URL_RE.match(controller._page.url)),"living":living,"session_id":session_id,"url":controller._page.url}
    try:
        return controller._call("_invoke",timeout=float(login_timeout_sec)+30,callback=work)
    except Exception as error:
        return {"status": "error", "message": str(error)}

