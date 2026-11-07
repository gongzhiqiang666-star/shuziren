import sys
import os
import asyncio

# 将项目根目录添加到sys.path中，以便能够正确地从assets.ws_danmu_capture.tb导入模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from assets.ws_danmu_capture.tb.taobao_danmu import TaobaoDanmu

def main():
    """主函数，用于启动弹幕服务器"""
    print("正在启动淘宝弹幕捕获 WebSocket 服务器包装器...")
    
    # 设置headless=False以显示浏览器窗口，方便处理登录或验证码
    danmu_client = TaobaoDanmu(headless=False)
    
    try:
        # 运行 TaobaoDanmu 实例中的 WebSocket 服务器
        asyncio.run(danmu_client.main_server())
    except KeyboardInterrupt:
        print("淘宝弹幕服务器被手动终止。")
    except Exception as e:
        # 捕获并打印其他可能的异常
        print(f"启动淘宝弹幕服务器时发生错误: {e}")

if __name__ == "__main__":
    main()
