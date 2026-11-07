import asyncio
import json
import re
from datetime import datetime
try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None
import logging
import os
import websockets
import time

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TaobaoDanmu:
    def __init__(self, headless=True):
        """
        初始化淘宝弹幕爬虫
        
        Args:
            headless (bool): 是否使用无头模式运行浏览器
        """
        self.playwright = None
        self.browser = None
        self.page = None
        self.headless = headless
        self.seen_comments = set()  # 用于去重

        # WebSocket server fields
        self.clients = set()
        self.playwright_task = None
        self._is_running = False
        
    async def broadcast(self, message):
        """向所有连接的客户端广播消息"""
        if self.clients:
            await websockets.broadcast(self.clients, json.dumps(message, ensure_ascii=False))

    def find_chrome_path(self):
        """查找Chrome浏览器路径"""
        possible_paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        ]
        if 'CHROME_PATH' in os.environ and os.path.exists(os.environ['CHROME_PATH']):
            return os.environ['CHROME_PATH']
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
        
    async def setup_browser(self):
        """设置Playwright浏览器"""
        try:
            if async_playwright is None:
                raise RuntimeError("缺少 playwright；请安装 playwright 并执行 playwright install chromium")
            self.playwright = await async_playwright().start()
            
            chrome_path = self.find_chrome_path()
            if not chrome_path:
                raise RuntimeError("未找到Chrome浏览器，请确保已安装或通过CHROME_PATH环境变量指定路径")

            # 启动浏览器，使用系统Chrome，添加反检测参数
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                executable_path=chrome_path,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    # '--disable-gpu', # 注释掉此行以启用GPU加速，显著降低CPU占用
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    # '--disable-features=VizDisplayCompositor', # 同样注释掉以确保GPU加速生效
                    '--window-size=800,600',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ]
            )
            
            # 创建页面上下文，添加反检测设置
            context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 800, 'height': 600},
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
            
            # 禁用图片加载以提高速度
            await context.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())
            
            self.page = await context.new_page()
            logger.info("Playwright浏览器初始化成功")
            
        except Exception as e:
            logger.error(f"初始化Playwright浏览器失败: {e}")
            raise
    
    async def handle_network_request(self, route):
        """处理网络请求，拦截弹幕API"""
        if 'mtop.taobao.iliad.comment.query.latest' not in route.request.url:
            await route.continue_()
            return

        try:
            response = await route.fetch()
            if not response:
                await route.abort()
                return

            if response.ok:
                text = await response.text()
                # 在后台任务中解析弹幕数据，以避免阻塞网络请求
                asyncio.create_task(self.parse_danmu_data(text))
            
            # 使用获取到的响应完成原始请求，这样浏览器端才能正常收到数据
            await route.fulfill(response=response)
        except Exception as e:
            logger.error(f"处理弹幕网络请求时出错: {e}")
            # 如果处理过程中发生错误，中止请求以防页面挂起
            if not route.is_handled():
                await route.abort()
    
    async def parse_danmu_data(self, response_text):
        """解析弹幕数据并广播"""
        try:
            # 提取JSON数据
            match = re.search(r'mtopjsonp\d+\((.+)\)', response_text)
            if match:
                data = json.loads(match.group(1))
                if data.get('data') and data['data'].get('comments'):
                    comments = data['data']['comments']
                    for comment in comments:
                        content = comment.get('content', '').strip()
                        if content:
                            # 转换时间戳
                            timestamp = int(comment.get('timestamp', '0')) / 1000
                            time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')
                            
                            # 获取用户名
                            username = comment.get('publisherNick', '匿名用户')

                            info = {
                                "type": "弹幕",
                                "nickname": username,
                                "content": content
                            }
                            await self.broadcast(info)
                            
                            # 打印弹幕到控制台用于调试
                            print(f"[{time_str}] {username}: {content}")
        except Exception as e:
            #logger.warning(f"解析弹幕数据时出错: {e}")
            print("")
    
    async def get_danmu_from_live(self, live_url):
        """
        从淘宝直播间获取弹幕
        
        Args:
            live_url (str): 直播间URL
        """
        if not self.browser:
            await self.setup_browser()
        
        try:
            logger.info(f"开始访问直播间: {live_url}")
            # 增加超时时间到60秒，使用domcontentloaded而不是networkidle
            await self.page.goto(live_url, wait_until='domcontentloaded', timeout=60000)
            
            # 等待页面加载
            await asyncio.sleep(3)
            
            # 检查是否有验证码
            try:
                # 查找验证码相关元素
                captcha_elements = await self.page.query_selector_all('div[class*="captcha"], div[class*="verify"], div[class*="slider"]')
                if captcha_elements:
                    logger.info("检测到验证码，请手动完成验证...")
                    print("检测到验证码，请在浏览器中手动完成验证，然后按回车继续...")
                    input("按回车键继续...")
                    await asyncio.sleep(2)
            except Exception:
                pass
            
            # 移除视频播放区域以降低资源消耗
            try:
                logger.info("尝试移除视频播放区域以降低资源消耗...")
                await self.page.evaluate('''() => {
                    const liveArea = document.querySelector('div[class*="liveArea"]');
                    if (liveArea) {
                        liveArea.remove();
                    }
                }''')
                logger.info("视频播放区域已成功移除。")
            except Exception as e:
                logger.warning(f"移除视频区域失败: {e}")

            logger.info("开始抓取弹幕...")
            
            # 添加网络监听
            await self.page.route("**/*", self.handle_network_request)
            
            while self._is_running:
                await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"获取弹幕失败: {e}")
        finally:
            await self.close_browser()

    async def stop(self):
        """停止浏览器和任务"""
        self._is_running = False
        if self.playwright_task and not self.playwright_task.done():
            self.playwright_task.cancel()
        await self.close_browser()

    async def close_browser(self):
        """关闭浏览器"""
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("浏览器已关闭")
        except Exception as e:
            logger.warning(f"关闭浏览器时出现错误: {e}")

    async def handler(self, websocket, path=None):
        """处理WebSocket连接"""
        self.clients.add(websocket)
        logger.info(f"新客户端连接: {websocket.remote_address}, 当前客户端数: {len(self.clients)}")
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if 'url' in data:
                        live_url = data['url']
                        if self.playwright_task is None or self.playwright_task.done():
                            logger.info(f"收到URL，启动Playwright: {live_url}")
                            self._is_running = True
                            self.playwright_task = asyncio.create_task(self.get_danmu_from_live(live_url))
                        else:
                            logger.warning("Playwright已在运行中，忽略新的URL")
                except json.JSONDecodeError:
                    logger.error(f"收到非JSON消息: {message}")
                except Exception as e:
                    logger.error(f"处理消息时出错: {e}")
            await websocket.wait_closed()
        finally:
            self.clients.remove(websocket)
            logger.info(f"客户端断开连接: {websocket.remote_address}, 当前客户端数: {len(self.clients)}")
            # if not self.clients and self.playwright_task:
            #     logger.info("最后一个客户端已断开，正在停止Playwright...")
            #     await self.stop()

    async def main_server(self, host="127.0.0.1", port=8888):
        """启动WebSocket服务器"""
        logger.info("启动 Taobao 弹幕服务器...")
        async with websockets.serve(self.handler, host, port):
            logger.info(f"WebSocket 服务器已启动，监听地址: ws://{host}:{port}")
            await asyncio.Future()  # 永久运行
