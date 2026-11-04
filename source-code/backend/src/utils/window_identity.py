"""本实例主窗口句柄的持有与捕获。

关闭相关的所有动作都只对这里保存的句柄操作，避免再用
`FindWindowW(None, "Comfyui-Box")` 按标题去猜窗口（双实例时会打到别的进程，
也可能命中 explorer 的 TabProxyWindow）。

捕获顺序：
1. pywebview 窗口对象自带的 native Form 句柄（本进程创建的那个窗口）；
2. 兜底：只枚举本进程（`os.getpid()`）的顶层窗口，按标题精确匹配，
   这条兜底同样不会跨进程。
"""

import os
import threading
from typing import Optional

from backend.src.utils.logger import app_logger as logger

_lock = threading.Lock()
_main_hwnd: int = 0


def set_main_window_hwnd(hwnd: int) -> None:
    """记录本实例主窗口句柄（模块级，跨模块共享）。"""
    global _main_hwnd
    with _lock:
        _main_hwnd = int(hwnd or 0)


def get_main_window_hwnd() -> int:
    """取本实例主窗口句柄，未捕获时返回 0。"""
    with _lock:
        return _main_hwnd


def clear_main_window_hwnd() -> None:
    """清空已记录的句柄（窗口销毁后调用）。"""
    set_main_window_hwnd(0)


def capture_main_window_hwnd(
    window,
    title: str = "Comfyui-Box",
    retries: int = 10,
    interval: float = 0.1,
) -> int:
    """在窗口创建后捕获本实例句柄并写入模块级变量。

    只接受本进程的窗口：先取 native Form 的 Handle，失败后按自身 PID 枚举。
    返回捕获到的句柄，失败返回 0。
    """
    for attempt in range(max(1, retries)):
        hwnd = _hwnd_from_native(window)
        if not hwnd:
            hwnd = _hwnd_from_own_process(title)
        if hwnd:
            set_main_window_hwnd(hwnd)
            logger.info(f"[WindowIdentity] 已捕获本实例窗口句柄: hwnd={hwnd} (尝试 {attempt + 1})")
            return hwnd
        if attempt + 1 < retries:
            import time
            time.sleep(interval)

    logger.warning("[WindowIdentity] 未能捕获本实例窗口句柄")
    return 0


def _hwnd_from_native(window) -> int:
    """取 pywebview 窗口对象 native Form 的 Handle（本进程自有窗口）。"""
    if window is None:
        return 0
    try:
        handle = window.native.Handle
        return int(handle.ToInt32() if hasattr(handle, "ToInt32") else handle)
    except Exception:
        return 0


def _hwnd_from_own_process(title: str) -> Optional[int]:
    """仅在本进程的顶层窗口里按标题查找（不跨进程、不用 FindWindowW）。"""
    try:
        from backend.src.utils.window_bounds import find_window_by_title
        return find_window_by_title(title, max_retries=1, retry_interval=0, exclude=("Floating",))
    except Exception as e:
        logger.debug(f"[WindowIdentity] 本进程窗口枚举失败: {e}")
        return None


def get_own_pid() -> int:
    return os.getpid()
