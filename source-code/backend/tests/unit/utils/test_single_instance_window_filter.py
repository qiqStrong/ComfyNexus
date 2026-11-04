"""单实例激活：候选窗口筛选纯函数测试。

覆盖 `select_candidate_window` 的排除规则与排序优先级，全部使用构造的
窗口信息列表，不依赖真实桌面/真实进程。
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_SOURCE_ROOT = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR), str(_SOURCE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.src.utils.single_instance import WindowInfo, select_candidate_window  # noqa: E402

APP = "Comfyui-Box"
SELF_PID = 1000


def _win(hwnd=1, pid=2000, process_name="python.exe", title=APP, visible=True, iconic=False):
    return WindowInfo(
        hwnd=hwnd,
        pid=pid,
        process_name=process_name,
        title=title,
        visible=visible,
        iconic=iconic,
    )


def test_empty_returns_none():
    assert select_candidate_window([], SELF_PID, APP) is None


def test_excludes_self_pid():
    """自己进程的窗口不能被当成"已有实例"，否则会激活/关闭到自己。"""
    assert select_candidate_window([_win(pid=SELF_PID)], SELF_PID, APP) is None


def test_excludes_explorer_tab_proxy_window():
    """explorer.exe 的 TabProxyWindow 标题与应用窗口相同，必须排除。"""
    windows = [
        _win(hwnd=11, pid=900, process_name="explorer.exe"),
        _win(hwnd=12, pid=2000, process_name="python.exe"),
    ]
    assert select_candidate_window(windows, SELF_PID, APP).hwnd == 12


def test_excludes_floating_window_title():
    windows = [_win(hwnd=21, title="Comfyui-Box-Floating", pid=2000)]
    assert select_candidate_window(windows, SELF_PID, APP) is None


def test_excludes_titles_not_starting_with_app_name():
    windows = [_win(hwnd=31, title="ComfyUI 控制台", pid=2000)]
    assert select_candidate_window(windows, SELF_PID, APP) is None


def test_prefers_exact_title():
    windows = [
        _win(hwnd=41, title="Comfyui-Box - 工作区", pid=2000),
        _win(hwnd=42, title=APP, pid=3000),
    ]
    assert select_candidate_window(windows, SELF_PID, APP).hwnd == 42


def test_prefers_visible_over_hidden():
    windows = [
        _win(hwnd=51, title=APP, pid=2000, visible=False),
        _win(hwnd=52, title=APP, pid=3000, visible=True),
    ]
    assert select_candidate_window(windows, SELF_PID, APP).hwnd == 52


def test_prefers_non_iconic():
    windows = [
        _win(hwnd=61, title=APP, pid=2000, iconic=True),
        _win(hwnd=62, title=APP, pid=3000, iconic=False),
    ]
    assert select_candidate_window(windows, SELF_PID, APP).hwnd == 62


def test_stable_order_keeps_enumeration_order():
    windows = [
        _win(hwnd=71, title=APP, pid=2000, iconic=True),
        _win(hwnd=72, title=APP, pid=3000, iconic=True),
    ]
    assert select_candidate_window(windows, SELF_PID, APP).hwnd == 71
