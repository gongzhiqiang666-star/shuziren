import tkinter as tk
from PIL import ImageGrab
import numpy as np

class CaptureWindow:
    def __init__(self):
        self.last_image = None
        self.root = None
        self.running = True
        self.x1 = self.y1 = self.x2 = self.y2 = 0  # 窗口坐标
        
    def _create_window(self):
        """创建透明捕获窗口"""
        self.root = tk.Tk()
        self.root.title("捕获区域")
        
        # 设置窗口样式
        self.root.attributes("-alpha", 0.3)  # 半透明
        self.root.attributes("-topmost", True)  # 始终置顶
        self.root.config(bg='red')  # 红色背景
        
        # 去除标准窗口装饰
        self.root.overrideredirect(True)
        
        # 添加拖动功能
        self.root.bind("<Button-1>", self.start_move)
        self.root.bind("<ButtonRelease-1>", self.stop_move)
        self.root.bind("<B1-Motion>", self.do_move)
        
        # 添加调整大小的控件
        self.add_resize_widgets()
        
        # 添加关闭按钮
        close_btn = tk.Button(self.root, text="×", bg="red", fg="white", 
                             command=self.destroy, font=("Arial", 12, "bold"),
                             relief="flat", padx=5, pady=0)
        close_btn.place(x=0, y=0)
        
        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        

        width = screen_width // 8
        height = screen_height // 4
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # 初始化坐标
        self.update_rect()
    
    def add_resize_widgets(self):
        """添加调整大小的控件"""
        # 创建四角的调整大小控件
        positions = {
            'nw': {'x': 0, 'y': 0, 'cursor': 'top_left_corner'},
            'ne': {'x': 1, 'y': 0, 'cursor': 'top_right_corner'},
            'sw': {'x': 0, 'y': 1, 'cursor': 'bottom_left_corner'},
            'se': {'x': 1, 'y': 1, 'cursor': 'bottom_right_corner'}
        }
        
        for name, pos in positions.items():
            handle = tk.Label(self.root, bg="white", width=1, height=1)
            handle.place(relx=pos['x'], rely=pos['y'], anchor=name)
            handle.configure(cursor=pos['cursor'])
            handle.bind("<Button-1>", lambda e, n=name: self.start_resize(e, n))
            handle.bind("<B1-Motion>", lambda e, n=name: self.do_resize(e, n))
            handle.bind("<ButtonRelease-1>", lambda e: self.update_rect())
    
    def start_move(self, event):
        """开始移动窗口"""
        self.x = event.x
        self.y = event.y
    
    def stop_move(self, event):
        """停止移动窗口"""
        self.update_rect()
    
    def do_move(self, event):
        """执行窗口移动"""
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")
    
    def start_resize(self, event, corner):
        """开始调整窗口大小"""
        self.start_x = event.x_root
        self.start_y = event.y_root
        self.start_width = self.root.winfo_width()
        self.start_height = self.root.winfo_height()
        self.start_pos_x = self.root.winfo_x()
        self.start_pos_y = self.root.winfo_y()
        self.resize_corner = corner
    
    def do_resize(self, event, corner):
        """执行窗口大小调整"""
        delta_x = event.x_root - self.start_x
        delta_y = event.y_root - self.start_y
        
        new_width = self.start_width
        new_height = self.start_height
        new_x = self.start_pos_x
        new_y = self.start_pos_y
        
        # 根据调整的角落更新窗口尺寸和位置
        if 'e' in corner:  # 右边
            new_width += delta_x
        if 'w' in corner:  # 左边
            new_width -= delta_x
            new_x += delta_x
        if 's' in corner:  # 下边
            new_height += delta_y
        if 'n' in corner:  # 上边
            new_height -= delta_y
            new_y += delta_y
        
        # 设置最小尺寸
        new_width = max(100, new_width)
        new_height = max(100, new_height)
        
        # 更新窗口几何属性
        self.root.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")
    
    def update_rect(self):
        """更新窗口矩形坐标"""
        if self.root:
            # 强制更新窗口信息
            self.root.update_idletasks()
            
            # 获取屏幕绝对坐标
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            
            self.x1 = x
            self.y1 = y
            self.x2 = x + width
            self.y2 = y + height
    
    def capture_screen(self, similarity_threshold=None):
        """获取窗口区域的屏幕内容并判断是否发生变化"""
        if not self.root:
            return {'image': None, 'changed': False}
            
        self.update_rect()  # 确保使用最新坐标
        rect = (self.x1, self.y1, self.x2, self.y2)
        
        try:
            # 确保坐标有效
            x1, y1, x2, y2 = rect
            if x2 <= x1 or y2 <= y1:
                return {'image': None, 'changed': False}
            
            # 尝试截图
            current_image = ImageGrab.grab(bbox=rect)
            current_array = np.array(current_image)
            
            if self.last_image is None:
                self.last_image = current_array
                return {'image': current_array, 'changed': True}
            
            # 检查图像尺寸
            if current_array.shape != self.last_image.shape:
                self.last_image = current_array
                return {'image': current_array, 'changed': True}
            
            # 如果没有指定相似度阈值，则认为内容已更改
            if similarity_threshold is None:
                self.last_image = current_array
                return {'image': current_array, 'changed': True}
            
            # 计算相似度
            similarity = np.mean(current_array == self.last_image)
            changed = similarity < similarity_threshold
            
            if changed:
                self.last_image = current_array
            
            return {'image': current_array, 'changed': changed}
            
        except Exception as e:
            print(f"截图失败: {e}")
            return {'image': None, 'changed': False}
    
    def run(self, on_ready=None):
        """运行窗口"""
        print("创建捕获窗口")
        self._create_window()
        
        # 进入主循环
        try:
            if on_ready is not None:
                self.root.after_idle(on_ready)
            self.root.mainloop()
        except Exception as e:
            print(f"窗口主循环异常: {e}")
    
    def destroy(self):
        """销毁窗口"""
        if self.root:
            self.running = False
            self.root.destroy()
            self.root = None
            self.last_image = None
    
    @property
    def rect(self):
        """获取窗口位置和大小"""
        if self.root:
            return (self.x1, self.y1, self.x2, self.y2)
        return None