"""WebView startup helpers recovered from main.pyd."""

import os
import time
from copy import deepcopy
from pathlib import Path


def append_timestamp(url):
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}t={int(time.time() * 1000)}"


DEVELOPMENT_ENVIRONMENT_CONFIG = {
    "webview_url": "http://localhost:5002/",
    "server_url": "http://127.0.0.1:5154/",
    "update_url": "http://111.230.31.15:5155/",
}
PRODUCTION_ENVIRONMENT_CONFIG = {
    "webview_url": "https://live-user-front-tk-0420.hjstream.com/",
    "server_url": "https://live-user-server-tk-0420.hjstream.com/",
    "update_url": "http://111.230.31.15:5155/",
}


def normalize_environment_config(config):
    environments = config.get("environments")
    environment = config.get("environment")
    if isinstance(environments, dict) and isinstance(environments.get(environment), dict):
        return config

    debug_mode = config.get("debug_mode", False)
    if isinstance(debug_mode, str):
        debug_mode = debug_mode.strip().lower() not in (
            "", "0", "false", "no", "off", "prod", "production"
        )
    config["environment"] = "development" if debug_mode else "production"
    config["environments"] = {
        "development": deepcopy(DEVELOPMENT_ENVIRONMENT_CONFIG),
        "production": deepcopy(PRODUCTION_ENVIRONMENT_CONFIG),
    }
    return config


def get_environment_config(config):
    normalized = normalize_environment_config(config)
    return normalized["environments"][normalized["environment"]]


def resolve_webview_url(config):
    return append_timestamp(get_environment_config(config)["webview_url"])


DEV_WEBVIEW_REMOTE_DEBUGGING_PORT = int(os.environ.get("HUANJING_WEBVIEW_DEBUG_PORT", "9222"))


def configure_webview_debugging():
    import webview

    webview.settings["REMOTE_DEBUGGING_PORT"] = DEV_WEBVIEW_REMOTE_DEBUGGING_PORT


def get_initial_window_size():
    width = 1400
    return width, int(width * 11 / 16)


def get_window_name(runtime_dir):
    path = Path(runtime_dir) / "assets" / "web" / "window_name.txt"
    try:
        return path.read_text(encoding="utf-8").strip() or "AI数字人直播"
    except (OSError, UnicodeError):
        return "AI数字人直播"


def run_webview(api, config, runtime_dir, *, debug=None):
    """Run the recovered window lifecycle for an initialized API instance."""
    import signal

    import webview

    from . import main_shutdown

    if debug is None:
        debug = os.environ.get("HUANJING_WEBVIEW_DEBUG", "").strip() == "1"

    signal.signal(signal.SIGINT, main_shutdown.force_exit)
    signal.signal(signal.SIGTERM, main_shutdown.force_exit)
    main_shutdown.api_for_exit = api
    width, height = get_initial_window_size()
    if debug:
        configure_webview_debugging()
    window = webview.create_window(
        get_window_name(runtime_dir),
        resolve_webview_url(config),
        js_api=api,
        width=width,
        height=height,
        resizable=True,
        frameless=False,
        min_size=(1200, 750),
    )
    window.events.closed += main_shutdown.make_on_closed(api)
    webview.start(debug=debug, private_mode=False)
