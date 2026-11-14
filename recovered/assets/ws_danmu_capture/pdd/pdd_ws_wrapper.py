import sys
import os
import asyncio
import argparse

# 将项目根目录添加到sys.path中，以便能够正确地从assets.ws_danmu_capture.pdd导入模块
# 脚本路径: assets/ws_danmu_capture/pdd/pdd_ws_wrapper.py
# 项目根目录是向上三层
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from assets.ws_danmu_capture.pdd.pinduoduo_danmu import PinduoduoDanmu

def main():
    """主函数，用于启动弹幕服务器"""
    print("正在启动拼多多弹幕捕获 WebSocket 服务器包装器...")
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--cookies")
    options = parser.parse_args()
    if not 1 <= options.port <= 65535:
        raise ValueError("无效的本地弹幕端口")
    danmu_client = PinduoduoDanmu()
    if options.cookies:
        danmu_client.cookies_path = os.fspath(os.path.abspath(os.path.expanduser(options.cookies)))
    
    try:
        # 运行 PinduoduoDanmu 实例中的 WebSocket 服务器
        asyncio.run(danmu_client.main_server(port=options.port))
    except KeyboardInterrupt:
        print("拼多多弹幕服务器被手动终止。")
    except Exception as e:
        # 捕获并打印其他可能的异常
        print(f"启动拼多多弹幕服务器时发生错误: {e}")

if __name__ == "__main__":
    main()
