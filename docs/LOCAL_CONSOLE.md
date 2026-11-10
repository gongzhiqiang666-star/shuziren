# 本地控制台

从仓库根目录使用 Python 3.10 或以上版本运行：

```powershell
python -X utf8 -m scripts.local_console
```

控制台仅监听 `127.0.0.1`，终端打印访问地址。默认端口5158，配置保存在LOCALAPPDATA/Shuziren/console.json。配置目录支持显式指定：

```powershell
python -X utf8 -m scripts.local_console --data-directory logs/validation/my-console --port 5158
```

端口参数仅覆盖本次监听端口；页面保存的端口下次启动生效。资源路径可填写运行包目录或其_internal目录，预检只检查8项必需文件是否存在，不执行商业程序、不修改原配置，也不验证哈希/GPU/模型/平台。

页面支持保存配置、检查资源和重新读取。刷新仅获取配置，不创建或启动直播。异常在页面显示；损坏配置不会被自动重置，可明确填写完整配置后保存修复。请求日志在数据目录console.log，不记录请求体或会话令牌。

当前在启动终端按Ctrl+C退出，服务端口由finally关闭。页面退出、单实例及后续工作进程回收在V01-04验收。这里只交付启动准备，尚未接入真实直播；不得将此页验收作为V05～V09通过证据。

验证：

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_local_console*.py' -v
```
