# A06-01 Windows 音频设备全局编号

验证日期：2026-11-14。环境：当前 Windows 本机、随包 Python/PyAudio。

## 修复

PortAudio 的 `get_device_info_by_host_api_device_index` 返回设备信息中的全局 `index`。旧实现却把 host API 内的局部循环序号交给后续播放器，在多 host API 环境可能打开错误设备。现改为返回设备信息的全局编号；枚举期间单个设备消失或查询失败只记录该设备错误并继续扫描，其余设备不再全部丢失。PyAudio 实例在成功和异常路径均终止。

恢复契约使用全局编号 99/98/97 的构造设备验证映射，并验证中间设备查询失败后仍返回前后两个可用设备。

## Windows 实测

真实枚举得到 2 个输入和 5 个输出。输出全局编号分别为 2、3、4、5、6，覆盖系统默认映射、NVIDIA Monitor、VB-Audio CABLE Input、VB-Audio 16ch 和 Realtek 扬声器。

逐个使用返回编号，以 48 kHz、16-bit、双声道打开 PortAudio 输出流，写入 100 ms 静音，随后 `stop_stream`、`close` 并 `terminate`。五个设备均成功打开和释放，退出码为 0。

本轮没有物理拔插设备，也未制造其他程序的独占占用，因此热插拔、独占冲突、播放中设备消失仍为 A06-01 待验项。
