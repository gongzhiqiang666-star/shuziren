# LIV-017 本地 SRS 验证

验证日期：2026-11-14  
环境：Windows，本机 `yunchuang_v122/_internal` 随包 SRS 与 FFmpeg。

## 实现结论

- 不再依赖 `srs-live.bat` 中已失效的注册表安装路径，直接从运行目录启动 `assets/srs/objs/srs.exe -c conf/live.conf`。
- 启动前检查 1935、1985、8080 端口，避免把其他程序的服务误认为本实例。
- 启动后同时检查进程早退与三个服务端口就绪；超时会回收本实例。
- 退出从全局 `taskkill /IM srs.exe` 改为 `taskkill /T /PID <owned pid>`，不会误杀其他项目的 SRS。
- `get_stream_urls` 保持原推流/播放地址，并新增 `local_service` 状态用于页面诊断。

## 自动验证

- `tests/test_srs_runtime.py`：6 项通过，覆盖缺失文件、端口冲突、异常早退、正常就绪、状态及 PID 定向回收。
- `tests/test_srs_integration.py`：真实随包 SRS 启动成功；1985 API 返回 HTTP 200；FFmpeg 向 `rtmp://127.0.0.1/live/integration` 推送 320×240/25fps H.264+AAC 测试源；从 `http://127.0.0.1:8080/live/integration.flv` 拉取并解码 1 秒成功；测试结束后三个监听端口均释放。

## 尚待最终验收

- 正式打包页面显示与按钮链路。
- 30 分钟以上推拉流、断流重连和资源曲线，按阶段约定放到首版完成后的集中稳定性测试。
