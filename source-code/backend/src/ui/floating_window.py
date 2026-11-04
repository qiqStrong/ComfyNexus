"""
悬浮窗管理器
管理悬浮窗的创建、销毁和位置
"""

import webview
import os
import time
import ctypes
import ctypes.wintypes
import threading
from typing import Optional, Tuple
from backend.src.utils.logger import app_logger as logger


class FloatingWindowManager:
    """悬浮窗管理器"""
    
    DEFAULT_WIDTH = 280
    DEFAULT_HEIGHT = 260
    DEFAULT_MARGIN = 40
    
    def __init__(self):
        self._window: Optional[webview.Window] = None
        self._api = None
        self._position: Optional[Tuple[int, int]] = None
        self._visible: bool = False
        self._target_x: int = 0
        self._target_y: int = 0
        self._initial_hidden: bool = True
        self._main_window: Optional[webview.Window] = None
        self._main_hwnd: Optional[int] = None
        self._watchdog_running: bool = False
        self._style_guardian_running: bool = False
        self._dpi_scale: float = 1.0
        self._settings_manager = None
    
    def set_api(self, api):
        """设置 API 实例"""
        self._api = api

    def set_settings_manager(self, settings_manager):
        """设置 SettingsManager 实例，用于持久化位置"""
        self._settings_manager = settings_manager

    def _save_current_position(self):
        """将当前窗口位置保存到配置文件"""
        if not self._settings_manager:
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "Comfyui-Box Floating")
            if not hwnd:
                return
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.pointer(rect))
            x = rect.left
            y = rect.top
            self._settings_manager.save_floating_window_position(x, y)
            logger.debug(f"[FloatingWindowManager] 位置已持久化: ({x}, {y})")
        except Exception as e:
            logger.debug(f"[FloatingWindowManager] 保存位置失败: {e}")
    
    def set_main_window(self, window: webview.Window):
        """设置主窗口引用，用于看门狗监控"""
        self._main_window = window
    
    def set_main_hwnd(self, hwnd: int):
        """设置主窗口句柄，用于多显示器定位"""
        self._main_hwnd = hwnd
    
    def _start_watchdog(self):
        """启动看门狗线程，监控主窗口是否存活"""
        if self._watchdog_running:
            return
        self._watchdog_running = True
        
        def watchdog():
            while self._watchdog_running and self._window is not None:
                time.sleep(0.5)
                try:
                    # 检查主窗口是否还在 pywebview 的窗口列表中
                    if self._main_window and self._main_window not in webview.windows:
                        logger.info("[FloatingWindowManager] 检测到主窗口已关闭，销毁悬浮窗并退出进程")
                        self.destroy()
                        time.sleep(0.5)
                        os._exit(0)
                except Exception:
                    pass
            self._watchdog_running = False
        
        t = threading.Thread(target=watchdog, name="FloatingWindowWatchdog", daemon=True)
        t.start()
    
    def _start_style_guardian(self):
        """启动样式守护定时器，确保 WS_EX_TOOLWINDOW 持续生效"""
        if self._style_guardian_running:
            return
        self._style_guardian_running = True
        
        def guardian():
            start_time = time.time()
            max_duration = 60
            interval = 0.1
            
            while self._style_guardian_running and self._window is not None:
                elapsed = time.time() - start_time
                if elapsed >= max_duration:
                    break
                
                try:
                    hwnd = ctypes.windll.user32.FindWindowW(None, "Comfyui-Box Floating")
                    if hwnd:
                        GWL_EXSTYLE = -20
                        WS_EX_TOOLWINDOW = 0x00000080
                        current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                        
                        if current_style & WS_EX_TOOLWINDOW:
                            # 样式已生效，停止守护
                            duration = time.time() - start_time
                            logger.info(f"[FloatingWindowManager] 样式守护完成，耗时 {duration:.1f}s，WS_EX_TOOLWINDOW 已稳定生效")
                            self._style_guardian_running = False
                            return
                        else:
                            # 样式丢失，重新应用
                            self._apply_toolwindow_style_internal(hwnd)
                            logger.debug(f"[FloatingWindowManager] 样式守护：重新应用 WS_EX_TOOLWINDOW (elapsed={elapsed:.1f}s)")
                except Exception:
                    pass
                
                time.sleep(interval)
            
            duration = time.time() - start_time
            self._style_guardian_running = False
            logger.info(f"[FloatingWindowManager] 样式守护定时器到期关闭，耗时 {duration:.1f}s")
        
        t = threading.Thread(target=guardian, name="StyleGuardian", daemon=True)
        t.start()
    
    def _get_monitor_work_area(self, hwnd: int = None) -> Tuple[int, int, int, int]:
        """
        获取指定窗口所在显示器的工作区
        
        Args:
            hwnd: 窗口句柄，如果为 None 则使用主窗口句柄
            
        Returns:
            Tuple[int, int, int, int]: (left, top, right, bottom) 工作区坐标（物理像素）
        """
        from backend.src.utils.window_bounds import MONITORINFO
        
        user32 = ctypes.windll.user32
        
        target_hwnd = hwnd or self._main_hwnd
        
        if target_hwnd:
            try:
                hmonitor = user32.MonitorFromWindow(target_hwnd, 2)
                monitor_info = MONITORINFO()
                monitor_info.cbSize = ctypes.sizeof(MONITORINFO)
                user32.GetMonitorInfoW(hmonitor, ctypes.pointer(monitor_info))
                
                work_area = monitor_info.rcWork
                logger.debug(f"[FloatingWindowManager] 获取显示器工作区: ({work_area.left}, {work_area.top}) - ({work_area.right}, {work_area.bottom})")
                return (work_area.left, work_area.top, work_area.right, work_area.bottom)
            except Exception as e:
                logger.warning(f"[FloatingWindowManager] 获取显示器工作区失败: {e}")
        
        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)
        logger.debug(f"[FloatingWindowManager] 使用主显示器尺寸: {screen_width}x{screen_height}")
        return (0, 0, screen_width, screen_height)
    
    def _calculate_position(self, work_area: Tuple[int, int, int, int], dpi_scale: float) -> Tuple[int, int]:
        """
        计算悬浮窗在指定工作区内的位置（右上角）
        
        Args:
            work_area: (left, top, right, bottom) 工作区坐标
            dpi_scale: DPI 缩放因子
            
        Returns:
            Tuple[int, int]: (x, y) 逻辑像素坐标
        """
        left, top, right, bottom = work_area
        work_width = right - left
        work_height = bottom - top
        
        if self._position:
            phys_x, phys_y = self._position
        else:
            phys_x = left + work_width - self.DEFAULT_WIDTH - self.DEFAULT_MARGIN
            phys_y = top + self.DEFAULT_MARGIN
        
        phys_x = max(left, min(phys_x, right - self.DEFAULT_WIDTH))
        phys_y = max(top, min(phys_y, bottom - self.DEFAULT_HEIGHT))
        
        logical_x = round(phys_x / dpi_scale)
        logical_y = round(phys_y / dpi_scale)
        
        logger.debug(f"[FloatingWindowManager] 位置计算: 工作区({left},{top},{right},{bottom}), 物理位置({phys_x},{phys_y}), 逻辑位置({logical_x},{logical_y})")
        
        return (logical_x, logical_y)
    
    def create_window(self, base_url: str, screen_width: int, screen_height: int, dpi_scale: float = 1.0, hidden: bool = True) -> Optional[webview.Window]:
        """
        创建悬浮窗
        
        Args:
            base_url: 基础 URL
            screen_width: 屏幕宽度（物理像素，仅作为降级使用）
            screen_height: 屏幕高度（物理像素，仅作为降级使用）
            dpi_scale: DPI 缩放因子
            hidden: 是否隐藏创建（默认 True）
            
        Returns:
            webview.Window 或 None
        """
        if self._window is not None:
            logger.warning("[FloatingWindowManager] 悬浮窗已存在")
            return self._window
        
        try:
            self._initial_hidden = hidden
            self._dpi_scale = dpi_scale
            
            if self._settings_manager:
                result = self._settings_manager.get_floating_window_position()
                if result.get("success") and result.get("position"):
                    saved = result["position"]
                    if isinstance(saved.get("x"), (int, float)) and isinstance(saved.get("y"), (int, float)):
                        self._position = (int(saved["x"]), int(saved["y"]))
                        logger.debug(f"[FloatingWindowManager] 从配置恢复位置: {self._position}")
            
            work_area = self._get_monitor_work_area()
            self._target_x, self._target_y = self._calculate_position(work_area, dpi_scale)
            
            logical_width = self.DEFAULT_WIDTH
            logical_height = self.DEFAULT_HEIGHT
            
            logger.info(f"[FloatingWindowManager] 创建窗口参数: dpi_scale={dpi_scale}, logical_size={logical_width}x{logical_height}")
            
            self._waiting_for_ready = True
            
            self._window = webview.create_window(
                'Comfyui-Box Floating',
                url=f'{base_url}/floating.html',
                width=logical_width,
                height=logical_height,
                x=-10000,
                y=-10000,
                frameless=True,
                transparent=True,
                on_top=True,
                easy_drag=True,
                hidden=False,
                js_api=self._api,
                min_size=(10, 10)
            )
            
            logger.info(f"[FloatingWindowManager] 悬浮窗已在屏幕外创建，目标位置：({self._target_x}, {self._target_y})")
            
            self._start_watchdog()
            self._start_style_guardian()
            
            return self._window
            
        except Exception as e:
            logger.error(f"[FloatingWindowManager] 创建悬浮窗失败：{e}")
            return None
    
    def configure_and_show(self):
        """配置窗口样式（在前端渲染完成后调用）"""
        try:
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi
            
            hwnd = 0
            for _ in range(10):
                hwnd = user32.FindWindowW(None, "Comfyui-Box Floating")
                if hwnd:
                    break
                time.sleep(0.1)
            
            if hwnd:
                try:
                    DWMWA_WINDOW_CORNER_PREFERENCE = 33
                    DWMWCP_ROUND = 2
                    
                    preference = ctypes.c_int(DWMWCP_ROUND)
                    dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        DWMWA_WINDOW_CORNER_PREFERENCE,
                        ctypes.byref(preference),
                        ctypes.sizeof(preference)
                    )
                    logger.debug("[FloatingWindowManager] 已设置窗口圆角")
                except Exception as corner_err:
                    logger.debug(f"[FloatingWindowManager] 设置圆角失败：{corner_err}")
                
                self._apply_toolwindow_style_internal(hwnd)
                logger.debug("[FloatingWindowManager] 已隐藏任务栏图标")
            else:
                logger.warning("[FloatingWindowManager] 未找到窗口句柄")
            
            self._waiting_for_ready = False
                
        except Exception as e:
            logger.error(f"[FloatingWindowManager] 配置窗口样式失败：{e}")
    
    def _apply_toolwindow_style_internal(self, hwnd: int):
        """内部样式应用方法（不处理异常和日志）"""
        user32 = ctypes.windll.user32
        
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style |= WS_EX_TOOLWINDOW
        ex_style &= ~WS_EX_APPWINDOW
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        
        SWP_FRAMECHANGED = 0x0020
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOZORDER = 0x0004
        SWP_SHOWWINDOW = 0x0040
        
        user32.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            SWP_FRAMECHANGED | SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_SHOWWINDOW
        )
    
    def _apply_toolwindow_style(self, delay_retry: bool = False):
        """
        应用任务栏图标隐藏样式
        
        Args:
            delay_retry: 是否使用延迟重试模式（在 show() 后 0.2 秒再次应用）
        """
        def _apply():
            try:
                user32 = ctypes.windll.user32
                
                max_retries = 3
                hwnd = 0
                
                for attempt in range(max_retries):
                    hwnd = user32.FindWindowW(None, "Comfyui-Box Floating")
                    if hwnd:
                        break
                    time.sleep(0.05)
                
                if not hwnd:
                    logger.warning("[FloatingWindowManager] 未找到窗口句柄，无法应用任务栏隐藏样式")
                    return
                
                self._apply_toolwindow_style_internal(hwnd)
                logger.debug("[FloatingWindowManager] 已设置 WS_EX_TOOLWINDOW 样式并强制刷新窗口框架")
                
                if delay_retry:
                    logger.debug("[FloatingWindowManager] 启动延迟重试（0.2 秒后再次应用样式）")
                    time.sleep(0.2)
                    self._apply_toolwindow_style(delay_retry=False)
                    
            except Exception as e:
                logger.error(f"[FloatingWindowManager] 应用任务栏图标隐藏样式失败：{e}")
        
        if delay_retry:
            threading.Thread(target=_apply, daemon=True).start()
        else:
            _apply()
    
    def finalize_setup(self, width: int = None, height: int = None):
        """前端渲染完毕后调用，重置透明层、恢复位置并调整最终尺寸
        
        注意：前端传递的是 CSS 像素（逻辑像素），需要转换为物理像素
        """
        if self._window is None:
            return
        
        try:
            logger.info(f"[FloatingWindowManager] finalize_setup() 开始执行，前端请求尺寸(CSS像素): {width}x{height}, dpi_scale={self._dpi_scale}")
            
            self._window.hide()
            logger.dev("[FloatingWindowManager] 已执行 hide() 刷新透明通道")
            
            if width and height:
                physical_width = round(width * self._dpi_scale)
                physical_height = round(height * self._dpi_scale)
                self._window.resize(physical_width, physical_height)
                logger.info(f"[FloatingWindowManager] resize() 调用完成，CSS像素: {width}x{height}, 物理像素: {physical_width}x{physical_height}")
            
            self._window.move(self._target_x, self._target_y)
            logger.dev(f"[FloatingWindowManager] 已移动到目标位置：({self._target_x}, {self._target_y})")
            
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "Comfyui-Box Floating")
            if hwnd:
                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.pointer(rect))
                actual_width = rect.right - rect.left
                actual_height = rect.bottom - rect.top
                logger.info(f"[FloatingWindowManager] 窗口实际物理尺寸: {actual_width}x{actual_height}")
            
            if not self._initial_hidden:
                hwnd = user32.FindWindowW(None, "Comfyui-Box Floating")
                if hwnd:
                    self._apply_toolwindow_style_internal(hwnd)
                self._window.show()
                self._visible = True
                hwnd_after = user32.FindWindowW(None, "Comfyui-Box Floating")
                if hwnd_after:
                    self._apply_toolwindow_style_internal(hwnd_after)
                logger.info("[FloatingWindowManager] 悬浮窗已归位并显示")
            else:
                logger.info("[FloatingWindowManager] 悬浮窗渲染就绪，根据配置保持隐藏")
                
        except Exception as e:
            logger.error(f"[FloatingWindowManager] finalize_setup 失败：{e}")
    
    def hide(self) -> bool:
        """隐藏悬浮窗（不销毁）"""
        if self._window:
            try:
                self._save_current_position()
                self._window.hide()
                self._visible = False
                logger.info("[FloatingWindowManager] 悬浮窗已隐藏")
                return True
            except Exception as e:
                logger.error(f"[FloatingWindowManager] 隐藏悬浮窗失败：{e}")
                return False
        return True
    
    def destroy(self) -> bool:
        """销毁悬浮窗（应用退出时调用）"""
        self._watchdog_running = False
        self._style_guardian_running = False
        if self._window is None:
            return True
        
        try:
            self._save_current_position()
            self._window.destroy()
            self._window = None
            logger.info("[FloatingWindowManager] 悬浮窗已销毁")
            return True
        except Exception as e:
            logger.error(f"[FloatingWindowManager] 销毁悬浮窗失败：{e}")
            self._window = None
            return False
    
    def set_position(self, x: int, y: int):
        """设置悬浮窗位置"""
        self._position = (x, y)
        
        if self._window:
            try:
                self._window.move(x, y)
                logger.debug(f"[FloatingWindowManager] 悬浮窗位置已更新：({x}, {y})")
            except Exception as e:
                logger.error(f"[FloatingWindowManager] 更新悬浮窗位置失败：{e}")
    
    def get_position(self) -> Optional[Tuple[int, int]]:
        """获取悬浮窗位置"""
        return self._position
    
    def resize_window(self, width: int, height: int) -> bool:
        """调整悬浮窗尺寸
        
        注意：前端传递的是 CSS 像素（逻辑像素），需要转换为物理像素
        """
        if self._window:
            try:
                current_width = getattr(self, '_current_width', self.DEFAULT_WIDTH)
                current_height = getattr(self, '_current_height', self.DEFAULT_HEIGHT)
                
                is_expanding = width > current_width or height > current_height
                
                physical_width = round(width * self._dpi_scale)
                physical_height = round(height * self._dpi_scale)
                self._window.resize(physical_width, physical_height)
                
                self._current_width = width
                self._current_height = height
                
                if is_expanding:
                    logger.debug(f"[FloatingWindowManager] 检测到窗口放大，强制刷新透明层")
                    self._window.hide()
                    self._window.show()
                    hwnd = ctypes.windll.user32.FindWindowW(None, "Comfyui-Box Floating")
                    if hwnd:
                        self._apply_toolwindow_style_internal(hwnd)
                    
                logger.info(f"[FloatingWindowManager] 窗口尺寸已调整：CSS像素 {width}x{height} -> 物理像素 {physical_width}x{physical_height}")
                return True
            except Exception as e:
                logger.error(f"[FloatingWindowManager] 调整窗口尺寸失败：{e}")
                return False
        return False
    
    def resize_window_safe(self, width: int, height: int, is_visible: bool) -> bool:
        """安全调整悬浮窗尺寸（带可见性检查）"""
        if not is_visible:
            logger.debug(f"[FloatingWindowManager] 窗口已隐藏，跳过 resize 操作")
            return True
        
        return self.resize_window(width, height)
    
    def is_visible(self) -> bool:
        """检查悬浮窗是否可见"""
        return self._window is not None


floating_window_manager = FloatingWindowManager()
