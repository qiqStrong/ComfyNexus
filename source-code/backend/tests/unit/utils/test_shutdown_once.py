"""幂等收尾器测试。

验证 `ShutdownOnce.run()`：只执行一次、重复调用返回 False、
单步异常不影响后续步骤，并留下可验收的日志痕迹。
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_SOURCE_ROOT = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR), str(_SOURCE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.src.utils.shutdown_once import ShutdownOnce  # noqa: E402


class _RecordingLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))


def test_runs_steps_once_and_skips_second_call():
    logger = _RecordingLogger()
    calls = []
    shutdown = ShutdownOnce(logger)

    steps = (
        ("a", lambda: calls.append("a")),
        ("b", lambda: calls.append("b")),
    )

    assert shutdown.run("closeApp", steps) is True
    assert shutdown.done is True
    assert calls == ["a", "b"]

    assert shutdown.run("closing", steps) is False
    assert calls == ["a", "b"], "第二次调用不应再执行任何收尾步骤"

    joined = "\n".join(message for _, message in logger.messages)
    assert "[_shutdown_once] 开始收尾 reason=closeApp" in joined
    assert "[_shutdown_once] 收尾完成 reason=closeApp" in joined
    assert "[_shutdown_once] 跳过（已执行，reason=closing）" in joined


def test_step_failure_does_not_block_later_steps():
    logger = _RecordingLogger()
    calls = []
    shutdown = ShutdownOnce(logger)

    def boom():
        raise RuntimeError("step failed")

    steps = (
        ("floating_window", boom),
        ("system_tray", lambda: calls.append("tray")),
    )

    assert shutdown.run("closing", steps) is True
    assert calls == ["tray"]

    warnings = [message for level, message in logger.messages if level == "warning"]
    assert any("步骤 floating_window 失败" in message for message in warnings)


def test_concurrent_run_executes_steps_only_once():
    import threading

    logger = _RecordingLogger()
    shutdown = ShutdownOnce(logger)
    calls = []
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        shutdown.run("race", (("step", lambda: calls.append(1)),))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == [1]
