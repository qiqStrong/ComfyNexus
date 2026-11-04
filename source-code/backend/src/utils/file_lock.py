"""
文件锁工具

提供跨平台的文件锁机制，支持 Windows 和 Unix 系统。

Author: Comfyui-Box 开发团队
Date: 2026-03-25
"""

import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, IO, Any

from backend.src.utils.logger import app_logger as logger


class FileLock:
    """
    跨平台文件锁
    
    支持 Windows (msvcrt) 和 Unix (fcntl) 系统。
    提供上下文管理器接口，简化使用。
    
    使用示例:
        with FileLock(file_path).lock():
            # 执行文件操作
            pass
    """
    
    def __init__(self, file_path: Path, timeout: float = 10.0):
        """
        初始化文件锁
        
        Args:
            file_path: 要锁定的文件路径
            timeout: 获取锁的超时时间（秒），默认 10 秒
        """
        self.file_path = Path(file_path)
        self.timeout = timeout
        self._file_obj: Optional[IO[Any]] = None
        self._locked = False
    
    @contextmanager
    def lock(self, exclusive: bool = True) -> Generator[None, None, None]:
        """
        获取文件锁的上下文管理器
        
        Args:
            exclusive: 是否为排他锁（写锁），默认 True
            
        Yields:
            None
        """
        self.acquire(exclusive)
        try:
            yield
        finally:
            self.release()
    
    def acquire(self, exclusive: bool = True) -> bool:
        """
        获取文件锁
        
        Args:
            exclusive: 是否为排他锁（写锁），默认 True
            
        Returns:
            是否成功获取锁
        """
        start_time = time.time()
        
        while True:
            try:
                if self._try_lock(exclusive):
                    self._locked = True
                    return True
            except Exception as e:
                logger.warning(f"[FileLock] 获取锁失败: {self.file_path}, {str(e)}")
            
            if time.time() - start_time > self.timeout:
                logger.error(f"[FileLock] 获取锁超时: {self.file_path}")
                return False
            
            time.sleep(0.05)
        
        return False
    
    def release(self) -> None:
        """释放文件锁"""
        if not self._locked:
            return
        
        try:
            if self._file_obj:
                self._unlock_file(self._file_obj)
                self._file_obj.close()
                self._file_obj = None
            self._locked = False
        except Exception as e:
            logger.warning(f"[FileLock] 释放锁失败: {self.file_path}, {str(e)}")
    
    def _try_lock(self, exclusive: bool) -> bool:
        """
        尝试获取文件锁
        
        Args:
            exclusive: 是否为排他锁
            
        Returns:
            是否成功
        """
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.touch()
        
        mode = 'r+' if exclusive else 'r'
        if exclusive and not self.file_path.exists():
            mode = 'w'
        
        self._file_obj = open(self.file_path, mode, encoding='utf-8')
        
        return self._lock_file(self._file_obj, exclusive)
    
    def _lock_file(self, file_obj: IO[Any], exclusive: bool) -> bool:
        """
        锁定文件（跨平台）
        
        Args:
            file_obj: 文件对象
            exclusive: 是否为排他锁
            
        Returns:
            是否成功
        """
        if sys.platform == 'win32':
            return self._lock_windows(file_obj, exclusive)
        else:
            return self._lock_unix(file_obj, exclusive)
    
    def _unlock_file(self, file_obj: IO[Any]) -> bool:
        """
        解锁文件（跨平台）
        
        Args:
            file_obj: 文件对象
            
        Returns:
            是否成功
        """
        if sys.platform == 'win32':
            return self._unlock_windows(file_obj)
        else:
            return self._unlock_unix(file_obj)
    
    def _lock_windows(self, file_obj: IO[Any], exclusive: bool) -> bool:
        """Windows 平台文件锁"""
        try:
            import msvcrt
            mode = msvcrt.LK_NBLCK if exclusive else msvcrt.LK_NBRLCK
            msvcrt.locking(file_obj.fileno(), mode, 1)
            return True
        except (OSError, IOError) as e:
            logger.debug(f"[FileLock] Windows 锁定失败: {str(e)}")
            return False
    
    def _unlock_windows(self, file_obj: IO[Any]) -> bool:
        """Windows 平台文件解锁"""
        try:
            import msvcrt
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
            return True
        except (OSError, IOError) as e:
            logger.debug(f"[FileLock] Windows 解锁失败: {str(e)}")
            return False
    
    def _lock_unix(self, file_obj: IO[Any], exclusive: bool) -> bool:
        """Unix 平台文件锁"""
        try:
            import fcntl
            lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(file_obj.fileno(), lock_type | fcntl.LOCK_NB)
            return True
        except (OSError, IOError) as e:
            logger.debug(f"[FileLock] Unix 锁定失败: {str(e)}")
            return False
    
    def _unlock_unix(self, file_obj: IO[Any]) -> bool:
        """Unix 平台文件解锁"""
        try:
            import fcntl
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
            return True
        except (OSError, IOError) as e:
            logger.debug(f"[FileLock] Unix 解锁失败: {str(e)}")
            return False


@contextmanager
def with_file_lock(file_path: Path, exclusive: bool = True, timeout: float = 10.0) -> Generator[None, None, None]:
    """
    文件锁上下文管理器（简化版）
    
    使用示例:
        with with_file_lock(cache_path):
            # 执行文件操作
            pass
    
    Args:
        file_path: 文件路径
        exclusive: 是否为排他锁，默认 True
        timeout: 超时时间（秒），默认 10 秒
        
    Yields:
        None
    """
    lock = FileLock(file_path, timeout)
    lock.acquire(exclusive)
    try:
        yield
    finally:
        lock.release()
