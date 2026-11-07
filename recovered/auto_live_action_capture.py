"""Recovered draggable screen-capture overlay."""

from __future__ import annotations

from queue import Empty

import numpy as np
from PIL import ImageGrab


class CaptureWindow:
    def __init__(self, command_queue=None, result_queue=None):
        self.command_queue = command_queue
        self.result_queue = result_queue
        self.root = None
        self.running = True
        self.last_image = None
        self.current_image = None
        self.x = self.y = self.width = self.height = 0
        self.start_x = self.start_y = 0
        self.start_pos_x = self.start_pos_y = 0
        self.start_width = self.start_height = 0
        self.resize_corner = None

    def _create_window(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.3)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = int(screen_width * 0.8)
        height = int(screen_height * 0.4)
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.bind("<Button-1>", self.start_move)
        self.root.bind("<ButtonRelease-1>", self.stop_move)
        self.root.bind("<B1-Motion>", self.do_move)
        self.close_btn = tk.Button(
            self.root, text="×", font=("Arial", 12, "bold"), bg="red", fg="white",
            relief="flat", command=self.destroy,
        )
        self.close_btn.place(relx=1, rely=0, anchor="ne", padx=5, pady=5)
        self.add_resize_widgets()
        self.update_rect()
        self.root.after(100, self._check_queue)

    def _check_queue(self):
        try:
            if self.running and self.command_queue is not None and not self.command_queue.empty():
                command = self.command_queue.get_nowait()
                if command == "capture":
                    result = self.capture_screen()
                    if self.result_queue:
                        self.result_queue.put({"image": result["image"], "pos": self.rect()})
                elif command == "stop":
                    self.destroy()
        except Empty:
            pass
        if self.running and self.root:
            self.root.after(100, self._check_queue)

    def add_resize_widgets(self):
        if not self.root:
            return
        import tkinter as tk
        for corner, cursor, x, y, anchor in (
            ("top_left_corner", "size_nw_se", 0, 0, "nw"),
            ("top_right_corner", "size_ne_sw", 1, 0, "ne"),
            ("bottom_left_corner", "size_ne_sw", 0, 1, "sw"),
            ("bottom_right_corner", "size_nw_se", 1, 1, "se"),
        ):
            widget = tk.Frame(self.root, width=14, height=14, bg="white", cursor=cursor)
            widget.place(relx=x, rely=y, anchor=anchor)
            widget.bind("<ButtonPress-1>", lambda event, c=corner: self.start_resize(event, c))
            widget.bind("<B1-Motion>", lambda event, c=corner: self.do_resize(event, c))

    def start_move(self, event):
        self.start_x, self.start_y = event.x_root, event.y_root

    def stop_move(self, event):
        self.update_rect()

    def do_move(self, event):
        deltax = event.x_root - self.start_x
        deltay = event.y_root - self.start_y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def start_resize(self, event, corner):
        self.resize_corner = corner
        self.start_x, self.start_y = event.x_root, event.y_root
        self.start_width, self.start_height = self.root.winfo_width(), self.root.winfo_height()
        self.start_pos_x, self.start_pos_y = self.root.winfo_x(), self.root.winfo_y()

    def do_resize(self, event, corner):
        dx, dy = event.x_root - self.start_x, event.y_root - self.start_y
        width, height = self.start_width, self.start_height
        x, y = self.start_pos_x, self.start_pos_y
        if "right" in corner:
            width += dx
        if "left" in corner:
            width -= dx
            x += dx
        if "bottom" in corner:
            height += dy
        if "top" in corner:
            height -= dy
            y += dy
        width, height = max(width, 20), max(height, 20)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.update_rect()

    def update_rect(self):
        if not self.root:
            return None
        self.root.update_idletasks()
        self.x = self.root.winfo_x()
        self.y = self.root.winfo_y()
        self.width = self.x + self.root.winfo_width()
        self.height = self.y + self.root.winfo_height()

    def capture_screen(self, similarity_threshold=None):
        if not self.running:
            return {"image": None, "changed": False}

        try:
            self.update_rect()
            bounds = self.rect()
            if bounds is None:
                return {"image": None, "changed": False}
            x, y, width, height = bounds
            if width <= x or height <= y:
                return {"image": None, "changed": False}

            image = ImageGrab.grab(bbox=(x, y, width, height))
            self.current_image = np.array(image)

            if self.last_image is None or self.current_image.shape != self.last_image.shape:
                self.last_image = self.current_image
                return {"image": self.current_image, "changed": True}

            if similarity_threshold is None:
                self.last_image = self.current_image
                return {"image": self.current_image, "changed": True}

            similarity = np.mean(self.current_image == self.last_image)
            changed = similarity < similarity_threshold
            if changed:
                self.last_image = self.current_image
            return {"image": self.current_image, "changed": changed}
        except Exception as exc:
            print(f"Capture error: {exc}")
            return {"image": None, "changed": False}

    def run(self):
        self._create_window()
        try:
            self.root.mainloop()
        except Exception as exc:
            print(f"Window error: {exc}")

    def destroy(self):
        self.running = False
        if self.root:
            self.root.destroy(); self.root = None
            self.last_image = None

    def rect(self):
        if not self.root:
            return None
        return (self.x, self.y, self.width, self.height)
