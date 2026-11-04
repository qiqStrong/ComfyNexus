"""GitManager 可用性解析顺序测试

覆盖：内置 MinGit → 系统 Git → 可用性否决。
全部通过 monkeypatch 隔离真实环境，不依赖本机是否安装 Git。
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_SOURCE_ROOT = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR), str(_SOURCE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.src.utils import git_manager as git_manager_module  # noqa: E402
from backend.src.utils.git_manager import GitManager, GitMode  # noqa: E402


class _FakeSettingsManager:
    """仅提供 GitMode 的桩，避免读取真实配置文件"""

    def __init__(self, mode: str = GitMode.MINGIT.value):
        self._mode = mode

    def get_git_mode(self) -> str:
        return self._mode


def _make_manager(mode: str = GitMode.MINGIT.value) -> GitManager:
    return GitManager(settings_manager=_FakeSettingsManager(mode))


def test_bundled_mingit_preferred(tmp_path, monkeypatch):
    """内置 MinGit 可用时优先使用，来源标记为 bundled"""
    mingit_dir = tmp_path / "MinGit"
    (mingit_dir / "cmd").mkdir(parents=True)
    (mingit_dir / "cmd" / "git.exe").write_bytes(b"")

    monkeypatch.setattr(git_manager_module, "get_mingit_dir", lambda: mingit_dir)
    monkeypatch.setattr(
        GitManager,
        "_verify_git_executable",
        lambda self, path: (True, "git version 2.53.0"),
    )

    status = _make_manager().check_availability()

    assert status.available is True
    assert status.mode == GitMode.MINGIT
    assert status.source == "bundled"
    assert status.path.endswith("git.exe")
    assert status.needs_setup is False


def test_system_git_fallback_when_mingit_missing(tmp_path, monkeypatch):
    """内置 MinGit 缺失但系统 Git 可用时，回退系统 Git 且视为可用"""
    mingit_dir = tmp_path / "MinGit"
    mingit_dir.mkdir()

    monkeypatch.setattr(git_manager_module, "get_mingit_dir", lambda: mingit_dir)
    monkeypatch.setattr(
        GitManager,
        "_verify_git_executable",
        lambda self, path: (True, "git version 2.50.0"),
    )
    monkeypatch.setattr(
        GitManager,
        "_find_system_git_path",
        lambda self: r"C:\Program Files\Git\cmd\git.exe",
    )

    status = _make_manager().check_availability()

    assert status.available is True
    assert status.mode == GitMode.SYSTEM
    assert status.source == "system"
    assert status.path == r"C:\Program Files\Git\cmd\git.exe"
    assert status.needs_setup is False


def test_no_git_available(tmp_path, monkeypatch):
    """内置与系统 Git 均不可用时判定为不可用"""
    mingit_dir = tmp_path / "MinGit"
    mingit_dir.mkdir()

    monkeypatch.setattr(git_manager_module, "get_mingit_dir", lambda: mingit_dir)
    monkeypatch.setattr(
        GitManager,
        "_verify_git_executable",
        lambda self, path: (False, "command not found"),
    )

    status = _make_manager().check_availability()

    assert status.available is False
    assert status.source == ""
    assert status.needs_setup is True
