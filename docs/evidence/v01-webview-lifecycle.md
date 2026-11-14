# SYS-005 WebView 生命周期验证

验证日期：2026-11-14

## 本轮修复

- `Api.shutdown()` 统一回收数字人、录播和脸手三类直播管理器，以及应用启动的场控助手、音频编辑器和本实例 SRS。
- 资源回收逐项隔离异常；一项失败不会阻止后续资源释放，并向调用方返回 `partial` 与错误列表。
- 关窗事件、SIGINT/SIGTERM、WebView 主循环正常返回和更新器启动均复用同一回收入口。
- 修复场控子进程初始化属性名与实际启停方法不一致的问题。

## 自动验证

`tests/test_main_webview_lifecycle.py` 共 4 项通过：

1. development 环境地址与毫秒时间戳。
2. WebView 窗口尺寸、最小尺寸、JS API、信号、关窗事件和启动参数。
3. 关窗时先执行资源回收，再退出进程。
4. 三类管理器、两个子进程与 SRS 的完整回收；单项失败后继续；重复调用不重复清理。

另有 `scripts/webview_smoke_host.py` 将当前本机预览作为开发环境 URL，并以原 `run_webview` 创建真实窗口；`tests/test_webview_smoke_host.py` 验证关窗标记原子写入。

## Windows 实机证据

- 本机随包 Python 和 pywebview 成功创建标题为“AI数字人直播”的真实窗口，窗口句柄非零且进程响应正常。
- 窗口加载地址指向当前 5257 隔离预览；该地址验证时返回 HTTP 200、33195 字节。
- Windows `CloseMainWindow` 返回 `true`，进程在 5 秒内退出；关窗回调标记显示 `shutdown_calls=1`，证明回收入口被执行且没有重复调用。
- 相同流程独立执行两次，第二次使用不同 PID 和标记文件，均正常退出。

## 待补实机证据

Windows Computer Use 在 2026-11-14 再次报告 `native pipe is unavailable: 系统找不到指定的文件 (os error 2)`。真实窗口创建和系统关窗已由进程级测试补验；无法使用旧坐标或绕过策略，因此不死循环等待，将以下交互项目保留到控制通道恢复后：

- 正式包页面内真实点击和前后端 JS 调用。
- 用户鼠标点击关闭、任务管理器结束和异常窗口场景。
- 页面当前版本的准备包预览、切换话术复审、载入轮播和场次报告已由本机 Chrome 复测通过，证据 `logs/validation/v08-preparation-ui-03`。Computer Use 原生管道缺失仅影响该控制工具，不再作为这条业务链的待验项。
