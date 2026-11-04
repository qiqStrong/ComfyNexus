"""Windows 单例运行工具

使用 Windows Mutex 确保应用只有一个实例运行。检测到已有实例时，只按
"PID + 进程映像名 + 标题" 精确筛选候选窗口（排除自身 PID、排除 explorer.exe），
绝不使用 FindWindowW 按标题盲取，避免双实例时激活/关闭到别的进程。

Mutex 创建失败不再静默当成首实例：区分 ERROR_ACCESS_DENIED，并用 OpenMutexW
探测锁是否真的已存在。
"""

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

HWND = wintypes.HWND
DWORD = wintypes.DWORD
BOOL = wintypes.BOOL
HANDLE = wintypes.HANDLE
LPCWSTR = wintypes.LPCWSTR

CreateMutexW = kernel32.CreateMutexW
CreateMutexW.argtypes = [ctypes.c_void_p, BOOL, LPCWSTR]
CreateMutexW.restype = HANDLE

OpenMutexW = kernel32.OpenMutexW
OpenMutexW.argtypes = [DWORD, BOOL, LPCWSTR]
OpenMutexW.restype = HANDLE

ReleaseMutex = kernel32.ReleaseMutex
ReleaseMutex.argtypes = [HANDLE]
ReleaseMutex.restype = BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [HANDLE]
CloseHandle.restype = BOOL

GetLastError = kernel32.GetLastError
GetLastError.argtypes = []
GetLastError.restype = DWORD

OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [DWORD, BOOL, DWORD]
OpenProcess.restype = HANDLE

QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW
QueryFullProcessImageNameW.argtypes = [HANDLE, DWORD, wintypes.LPWSTR, ctypes.POINTER(DWORD)]
QueryFullProcessImageNameW.restype = BOOL

EnumWindows = user32.EnumWindows
EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
EnumWindows.restype = BOOL

GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(DWORD)]
GetWindowThreadProcessId.restype = DWORD

GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
GetWindowTextW.restype = ctypes.c_int

GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowTextLengthW.argtypes = [HWND]
GetWindowTextLengthW.restype = ctypes.c_int

IsWindowVisible = user32.IsWindowVisible
IsWindowVisible.argtypes = [HWND]
IsWindowVisible.restype = BOOL

ShowWindow = user32.ShowWindow
ShowWindow.argtypes = [HWND, ctypes.c_int]
ShowWindow.restype = BOOL

SetForegroundWindow = user32.SetForegroundWindow
SetForegroundWindow.argtypes = [HWND]
SetForegroundWindow.restype = BOOL

IsIconic = user32.IsIconic
IsIconic.argtypes = [HWND]
IsIconic.restype = BOOL

WNDENUMPROC = ctypes.WINFUNCTYPE(BOOL, HWND, wintypes.LPARAM)

ERROR_ALREADY_EXISTS = 183
ERROR_ACCESS_DENIED = 5
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
SW_RESTORE = 9
SW_SHOW = 5

# 激活已有实例时，这些进程的窗口一律不算候选（explorer 会为任务栏创建
# Windows.Internal.Shell.TabProxyWindow，标题与应用窗口相同）
DEFAULT_DENIED_PROCESS_NAMES = ("explorer.exe",)
DEFAULT_EXCLUDED_TITLE_PARTS = ("Floating",)


@dataclass(frozen=True)
class WindowInfo:
    """候选窗口信息（纯数据，便于单测）。"""

    hwnd: int
    pid: int
    process_name: str
    title: str
    visible: bool
    iconic: bool = False


def _process_name(pid: int) -> str:
    """取进程映像文件名（小写，取 basename），失败返回空串。"""
    if not pid:
        return ""
    handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, DWORD(pid))
    if not handle:
        return ""
    try:
        size = DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return os.path.basename(buffer.value).lower()
    finally:
        CloseHandle(handle)


def _window_title(hwnd: int) -> str:
    length = GetWindowTextLengthW(HWND(hwnd))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(HWND(hwnd), buffer, length + 1)
    return buffer.value


def enumerate_top_level_windows() -> List[WindowInfo]:
    """枚举当前桌面的顶层窗口（附带 PID、进程映像名、标题、可见性）。"""
    windows: List[WindowInfo] = []
    process_name_cache: dict = {}

    @WNDENUMPROC
    def callback(hwnd, _lparam):
        pid = DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_value = int(pid.value)

        title = _window_title(int(hwnd))
        if not title:
            return True

        if pid_value not in process_name_cache:
            process_name_cache[pid_value] = _process_name(pid_value)

        windows.append(
            WindowInfo(
                hwnd=int(hwnd),
                pid=pid_value,
                process_name=process_name_cache[pid_value],
                title=title,
                visible=bool(IsWindowVisible(hwnd)),
                iconic=bool(IsIconic(hwnd)),
            )
        )
        return True

    EnumWindows(callback, 0)
    return windows


def select_candidate_window(
    windows: Iterable[WindowInfo],
    self_pid: int,
    app_name: str,
    denied_process_names: Sequence[str] = DEFAULT_DENIED_PROCESS_NAMES,
    excluded_title_parts: Sequence[str] = DEFAULT_EXCLUDED_TITLE_PARTS,
) -> Optional[WindowInfo]:
    """从窗口列表中挑选"已有实例"的主窗口（纯函数，不依赖真实桌面）。

    规则：
    - 排除自身 PID；
    - 排除 denied_process_names（默认 explorer.exe）；
    - 标题必须以 app_name 开头，且不含 excluded_title_parts（默认悬浮窗）；
    - 排序优先级：标题完全相等 > 可见 > 未最小化 > 枚举顺序靠前。
    """
    denied = {name.lower() for name in denied_process_names}
    candidates: List[WindowInfo] = []

    for window in windows:
        if window.pid == self_pid:
            continue
        if (window.process_name or "").lower() in denied:
            continue
        title = window.title or ""
        if not title.startswith(app_name):
            continue
        if any(part in title for part in excluded_title_parts):
            continue
        candidates.append(window)

    if not candidates:
        return None

    def rank(window: WindowInfo) -> tuple:
        return (
            0 if window.title == app_name else 1,
            0 if window.visible else 1,
            0 if not window.iconic else 1,
        )

    # sorted 是稳定排序，同等条件下保留枚举顺序
    return sorted(candidates, key=rank)[0]


class SingleInstance:
    """Windows 单例运行管理器。"""

    def __init__(self, app_name: str = "Comfyui-Box"):
        self.app_name = app_name
        self.mutex_name = f"Global\\{app_name}_SingleInstance_Mutex"
        self.mutex_handle: Optional[HANDLE] = None
        self._is_first_instance: Optional[bool] = None
        self._degraded = False

    @property
    def degraded(self) -> bool:
        """Mutex 无法创建时的降级标记（单实例保护不完整）。"""
        return self._degraded

    def try_acquire(self) -> bool:
        """尝试获取单例锁。

        Returns:
            bool: True 表示是第一个实例，False 表示已有实例运行。
        """
        if self._is_first_instance is not None:
            return self._is_first_instance

        self.mutex_handle = CreateMutexW(None, False, self.mutex_name)

        if not self.mutex_handle:
            last_error = GetLastError()
            if last_error == ERROR_ACCESS_DENIED:
                if self._mutex_exists():
                    self._is_first_instance = False
                    _safe_print("[启动] 全局 Mutex 无创建权限但已存在，判定为第二实例")
                    self._activate_existing_window()
                    return False
                self._degraded = True
                _safe_print(
                    "[警告] 无法创建全局 Mutex（ERROR_ACCESS_DENIED），"
                    "单实例保护已降级，继续以首实例启动"
                )
                self._is_first_instance = True
                return True

            self._degraded = True
            _safe_print(f"[警告] 创建单例 Mutex 失败，错误码={last_error}，单实例保护已降级")
            self._is_first_instance = True
            return True

        if GetLastError() == ERROR_ALREADY_EXISTS:
            self._is_first_instance = False
            self._activate_existing_window()
            return False

        self._is_first_instance = True
        return True

    def _mutex_exists(self) -> bool:
        """用 OpenMutexW 探测锁是否真的已存在（只探测，不持有）。"""
        if not self.mutex_name:
            return False
        handle = OpenMutexW(SYNCHRONIZE, False, self.mutex_name)
        if handle:
            CloseHandle(handle)
            return True
        return False

    def _activate_existing_window(self) -> bool:
        """激活已存在实例的主窗口；找不到就安静退出。"""
        try:
            candidate = select_candidate_window(
                enumerate_top_level_windows(),
                self_pid=os.getpid(),
                app_name=self.app_name,
            )
        except Exception as e:
            _safe_print(f"[启动] 枚举已有实例窗口失败: {e}")
            return False

        if not candidate:
            _safe_print("[启动] 未找到可激活的已有实例窗口，当前实例将退出")
            return False

        try:
            if candidate.iconic:
                ShowWindow(HWND(candidate.hwnd), SW_RESTORE)
            else:
                ShowWindow(HWND(candidate.hwnd), SW_SHOW)
            SetForegroundWindow(HWND(candidate.hwnd))
            _safe_print(
                f"[启动] 已激活已有实例窗口: hwnd={candidate.hwnd}, pid={candidate.pid}"
            )
            return True
        except Exception as e:
            _safe_print(f"[启动] 激活已有实例窗口失败: {e}")
            return False

    def release(self):
        """释放单例锁（退出时调用）。"""
        if self.mutex_handle:
            ReleaseMutex(self.mutex_handle)
            CloseHandle(self.mutex_handle)
            self.mutex_handle = None
            self._is_first_instance = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


def _safe_print(message: str) -> None:
    if getattr(sys, "frozen", False) and sys.executable.lower().endswith("pythonw.exe"):
        return
    try:
        print(message, flush=True)
    except Exception:
        pass


def check_single_instance(app_name: str = "Comfyui-Box") -> Optional[SingleInstance]:
    """检查是否为单例运行；已有实例时返回 None。"""
    instance = SingleInstance(app_name)
    if instance.try_acquire():
        return instance
    return None


def ensure_single_instance(app_name: str = "Comfyui-Box") -> tuple:
    """确保单例运行，返回 (是否首实例, 管理器)。"""
    instance = SingleInstance(app_name)
    is_first = instance.try_acquire()
    return is_first, instance if is_first else None
