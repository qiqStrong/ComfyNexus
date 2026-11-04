"""
Windows 单例运行工具

使用 Windows Mutex 确保应用只有一个实例运行。
如果已有实例运行，则激活已存在的窗口并退出当前实例。
"""

import sys
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

HWND = wintypes.HWND
DWORD = wintypes.DWORD
LPWSTR = wintypes.LPWSTR
LPCWSTR = wintypes.LPCWSTR
HANDLE = wintypes.HANDLE
BOOL = wintypes.BOOL

CreateMutexW = kernel32.CreateMutexW
CreateMutexW.argtypes = [ctypes.c_void_p, BOOL, LPCWSTR]
CreateMutexW.restype = HANDLE

ReleaseMutex = kernel32.ReleaseMutex
ReleaseMutex.argtypes = [HANDLE]
ReleaseMutex.restype = BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [HANDLE]
CloseHandle.restype = BOOL

GetLastError = kernel32.GetLastError
GetLastError.argtypes = []
GetLastError.restype = DWORD

FindWindowW = user32.FindWindowW
FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
FindWindowW.restype = HWND

SetForegroundWindow = user32.SetForegroundWindow
SetForegroundWindow.argtypes = [HWND]
SetForegroundWindow.restype = BOOL

ShowWindow = user32.ShowWindow
ShowWindow.argtypes = [HWND, ctypes.c_int]
ShowWindow.restype = BOOL

IsIconic = user32.IsIconic
IsIconic.argtypes = [HWND]
IsIconic.restype = BOOL

ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
SW_SHOW = 5


class SingleInstance:
    """
    Windows 单例运行管理器
    
    使用 Mutex 确保只有一个应用实例运行。
    当检测到已有实例时，会激活已存在的窗口并返回 False。
    """
    
    def __init__(self, app_name: str = "Comfyui-Box"):
        self.app_name = app_name
        self.mutex_name = f"Global\\{app_name}_SingleInstance_Mutex"
        self.mutex_handle: Optional[HANDLE] = None
        self._is_first_instance: Optional[bool] = None
    
    def try_acquire(self) -> bool:
        """
        尝试获取单例锁
        
        Returns:
            bool: True 表示是第一个实例，False 表示已有实例运行
        """
        if self._is_first_instance is not None:
            return self._is_first_instance
        
        self.mutex_handle = CreateMutexW(None, False, self.mutex_name)
        
        if not self.mutex_handle:
            return True
        
        last_error = GetLastError()
        
        if last_error == ERROR_ALREADY_EXISTS:
            self._is_first_instance = False
            self._activate_existing_window()
            return False
        
        self._is_first_instance = True
        return True
    
    def _activate_existing_window(self):
        """
        激活已存在的窗口
        
        查找并激活已运行实例的主窗口。
        """
        hwnd = FindWindowW(None, self.app_name)
        
        if hwnd and hwnd != 0:
            if IsIconic(hwnd):
                ShowWindow(hwnd, SW_RESTORE)
            else:
                ShowWindow(hwnd, SW_SHOW)
            
            SetForegroundWindow(hwnd)
    
    def release(self):
        """
        释放单例锁
        
        在应用退出时调用，释放 Mutex。
        """
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


def check_single_instance(app_name: str = "Comfyui-Box") -> Optional[SingleInstance]:
    """
    检查是否为单例运行
    
    Args:
        app_name: 应用名称，用于 Mutex 命名和窗口查找
    
    Returns:
        SingleInstance: 如果是第一个实例，返回管理器对象（需要在退出时调用 release）
        None: 如果已有实例运行，返回 None
    """
    instance = SingleInstance(app_name)
    
    if instance.try_acquire():
        return instance
    
    return None


def ensure_single_instance(app_name: str = "Comfyui-Box") -> tuple[bool, Optional[SingleInstance]]:
    """
    确保单例运行
    
    便捷函数，返回是否为第一个实例以及管理器对象。
    
    Args:
        app_name: 应用名称
    
    Returns:
        tuple: (is_first_instance, instance_manager)
            - is_first_instance: True 表示是第一个实例
            - instance_manager: 单例管理器对象，需要在应用退出时释放
    """
    instance = SingleInstance(app_name)
    is_first = instance.try_acquire()
    return is_first, instance if is_first else None
