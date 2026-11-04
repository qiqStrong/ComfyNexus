"""幂等收尾执行器。

把所有退出路径（确认框确认、closeApp、closing 事件、托盘退出、异常退出、
超时兜底）收敛到同一个 `ShutdownOnce.run()`：带锁 + 只执行一次，
每个步骤独立 try，单步失败不影响后续步骤。
"""

import threading
from typing import Callable, Iterable, Tuple


class ShutdownOnce:
    """带锁的幂等收尾器（进程内共享一个实例）。"""

    def __init__(self, logger) -> None:
        self._logger = logger
        self._lock = threading.Lock()
        self._done = False

    @property
    def done(self) -> bool:
        with self._lock:
            return self._done

    def run(self, reason: str, steps: Iterable[Tuple[str, Callable[[], None]]]) -> bool:
        """执行收尾步骤。

        Returns:
            bool: True 表示本次真正执行了收尾；False 表示已执行过而跳过。
        """
        with self._lock:
            if self._done:
                self._logger.info(f"[_shutdown_once] 跳过（已执行，reason={reason}）")
                return False
            self._done = True

        self._logger.info(f"[_shutdown_once] 开始收尾 reason={reason}")
        for name, step in steps:
            try:
                step()
            except Exception as e:
                self._logger.warning(f"[_shutdown_once] 步骤 {name} 失败: {e}")
        self._logger.info(f"[_shutdown_once] 收尾完成 reason={reason}")
        return True
