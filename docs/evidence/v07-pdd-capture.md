# LIV-010 拼多多弹幕采集

验证日期：2026-11-14

## 调用链修复

原恢复版在 `pinduoduo` 分支创建通用 `BarrageCapture(platform_type, url=live_url)`，会把拼多多网页地址直接当作 WebSocket 服务连接；随包 `pdd_ws_wrapper` 实际没有被管理器启动。因此原 protobuf 解析单测通过并不能证明产品入口可用。

现有链路为：

`DigitalLiveManager.start_danmu` → `PinduoduoDanmuBridge` → 动态回环端口上的随包 wrapper → 向 wrapper 发送官方直播 URL → Playwright 监听页面 WebSocket → 有界解析 protobuf/gzip → 本地广播 → 统一互动消息。

## 稳定性与安全边界

- 每次从回环地址选择空闲端口并将端口显式传给 wrapper，不固定占用 8888，不连接或终止无关服务。
- 直播地址仅接受 `pinduoduo.com`、`yangkeduo.com` 及真实子域的 HTTPS URL，拒绝 HTTP、凭据和相似恶意域名。
- Cookie 默认写入 `%LOCALAPPDATA%/Shuziren/pdd_cookies.json`，不再污染只读安装目录或源码树。
- `websockets.broadcast` 同步/异步版本均兼容；中文弹幕、进场、关注、点赞、礼物规范化为产品互动事件。
- 单帧、声明 body 和 gzip 解压结果均限制为 8 MiB；截断长度和压缩炸弹不会进入 protobuf/JSON 解析。
- wrapper 子进程由 bridge 持有，连接失败会回收，停止时关闭 socket 并有界终止/强杀自身进程。

## 验证

- `tests/test_pdd_bridge.py` 7 项通过：官方 URL、动态端口与 URL 交接、事件规范化、用户数据 Cookie、同步 broadcast、截断/超限压缩帧、管理器选择/启停。
- 使用独立媒体 Python 实际启动 wrapper，动态端口 `57826` 建立 WebSocket，随后 bridge 停止并确认子进程句柄清空；未发送直播 URL，因此没有打开浏览器或访问平台。
- 完整恢复契约继续覆盖 gzip + protobuf `Command` + `live_chat` 样本并验证用户/文本输出。

真实账号扫码、Cookie 续用、真实直播间弹幕、平台协议变化和断网重连仍需授权账号验证，不能据此标记 Windows/端到端完成。
