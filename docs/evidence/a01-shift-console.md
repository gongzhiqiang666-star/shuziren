# A01-04 换班控制台验证

## A01-05 浏览器 RTMP、轮播与接收组合链

- `scripts/validate_live_orchestration.py` 新增可选 `--browser-actions`，只在显式启用时让本机 Chrome 完成首场开播、首轮轮播配置和停播；状态观察、插播、接管恢复、历史及报告核验继续使用真实服务接口。
- `scripts/validate_browser_rtmp_rotation.py` 持有并回收随包 SRS 与 FFmpeg 循环推流进程，避免外部后台进程或 shell 参数传递成为隐式前置。
- `logs/validation/a01-browser-rtmp-rotation-02/result.json` 为通过报告：Chrome 三项动作均为真，场次输出 1,492 帧，4 条轮播记录、4 条控制记录及准备包报告一致。
- `receiver.mkv` 经 FFprobe/FFmpeg 验证为 35.018 秒、720×1280 FFV1 视频与 48 kHz 单声道 PCM 音频，完整解码通过；验证结束后 SRS 1935 端口不再监听。
- `a01-browser-rtmp-rotation-01` 保留首次失败：页面动作已送达，但 PowerShell 启动的发布源没有把首帧送入 SRS。修正的是验证进程所有权和参数传递，不修改产品 RTMP 超时语义。

范围限制：这是本机短时组合链，不代表公网弱网、30 分钟连续性或动态口型人工画质通过。

## 结论

本地控制台已能从浏览器完成两件商品的班次配置：每班独立时长、沿用场次主播或指定换班音色、助播音色选择，以及配置到直播服务层的交接。非法的 0 秒班次在浏览器端被拒绝，没有进入直播管理器。

## 本机证据

- 浏览器验证：`logs/validation/a01-shift-ui-02/result.json`
- 页面截图：`logs/validation/a01-shift-ui-02/shift-configuration.png`
- 服务层收到商品顺序、`shift_durations=[1,2]` 和第二班独立音色；页面显示“轮播中”和“第 1 班”。
- `test_console_live_rotation.py` 14/14、`test_tts_task_state.py` 12/12 通过，覆盖商品边界换班、轮换音色及合成任务绑定。
- 恢复层既有可控时钟回归覆盖 20 次班次交替。

本次浏览器验证使用本机夹具直播管理器，证明页面到服务层的配置协议，不冒充物理声卡输出或人工音色听审。

既有真实运行 `logs/validation/a01-timed-shifts-live-20-01/result.json` 已重新核验：ZipVoice 配置两条摘要不同的参考音，完成 20 次换班并记录首班在内 21 个严格交替的 `shift_index` 与商品；同场包含手动接管/恢复，末次任务记录 `reference_switch_count=1`。VB-Audio/虚拟摄像头回采为 450 秒、720×1280 FFV1 + 48 kHz 单声道 PCM，本轮使用 FFmpeg `-xerror` 全量解码退出 0。该证据关闭 20 次真实调度和设备回采缺口；是否符合目标音色、听感及观众端主观串音仍须人工听审，不能由任务元数据替代。
