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

- `tests/test_srs_runtime.py`：7 项通过，覆盖缺失文件、端口冲突、异常早退、正常就绪、状态、PID 定向回收，以及 `taskkill` 超时后仍按自有进程句柄强制回收并等待退出。
- `tests/test_srs_integration.py`：真实随包 SRS 启动成功；1985 API 返回 HTTP 200；FFmpeg 向 `rtmp://127.0.0.1/live/integration` 推送 320×240/25fps H.264+AAC 测试源；从 `http://127.0.0.1:8080/live/integration.flv` 拉取并解码 1 秒成功；测试结束后三个监听端口均释放。

2026-11-14 A04-03 复验：使用当前随包 SRS 和 FFmpeg 重跑真实推拉流通过，并将 1935/1985/8080 三端口释放检查写入集成断言，不再只以父进程退出代替服务释放。修复 Windows `taskkill` 超时或启动失败时提前抛出、跳过后备回收的问题；专项 7 项、真实集成 1 项及恢复基线五关通过。既有发布端停推再推、解码器异常重连与回采时间戳证据继续关联 A01-05；公网弱网和真实平台网络仍按外部环境待验。

## 尚待最终验收

- 正式打包页面显示与按钮链路。
- 30 分钟以上推拉流、断流重连和资源曲线，按阶段约定放到首版完成后的集中稳定性测试。
