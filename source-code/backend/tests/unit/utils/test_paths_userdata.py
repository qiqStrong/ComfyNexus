"""
用户数据根定位测试

覆盖：机器级指针 > 默认目录 > 临时降级；指针失效提示；显式 override 注入；用户级目录派生。
全部通过 monkeypatch 隔离真实环境，不读取进程环境变量。
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_SOURCE_ROOT = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR), str(_SOURCE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from backend.src.utils import paths  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_machine_dirs(monkeypatch, tmp_path):
    """把 LOCALAPPDATA 指向临时目录，避免读写真实机器级目录。"""
    local = tmp_path / "localappdata"
    local.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("APPDATA", raising=False)
    paths.reset_user_data_root_cache()
    yield
    paths.reset_user_data_root_cache()


def test_default_root_and_source(tmp_path):
    expected = Path(__import__("os").environ["LOCALAPPDATA"]) / paths.APP_NAME / "userdata"
    assert paths.get_user_data_root() == expected.resolve()
    assert paths.get_user_data_source() == "default"
    assert paths.get_default_user_data_root() == expected


def test_explicit_override_is_used(tmp_path):
    """自动化测试通过显式参数注入目录，不依赖进程环境变量。"""
    custom = tmp_path / "custom-root"
    root, source, note = paths.resolve_user_root(override=custom)
    assert root == custom.resolve()
    assert source == "override"
    assert note is None
    assert paths.get_user_data_root(override=custom) == custom.resolve()


def test_pointer_used_when_no_override(tmp_path):
    custom = tmp_path / "pointer-root"
    paths.write_userdata_pointer(custom)
    paths.reset_user_data_root_cache()
    assert paths.get_user_data_root() == custom.resolve()
    assert paths.get_user_data_source() == "pointer"
    assert paths.get_user_data_resolution_note() is None


def test_invalid_pointer_falls_back_to_default_with_note(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file, not dir", encoding="utf-8")
    paths.write_userdata_pointer(blocker / "cannot-create")
    paths.reset_user_data_root_cache()
    assert paths.get_user_data_root() == paths.get_default_user_data_root().resolve()
    assert paths.get_user_data_source() == "default"
    note = paths.get_user_data_resolution_note()
    assert note and "原数据目录不可用" in note


def test_fallback_to_temp_when_default_unwritable(monkeypatch, tmp_path):
    blocker = tmp_path / "blocked-default"
    blocker.write_text("file, not dir", encoding="utf-8")
    fake_temp = tmp_path / "temp"
    fake_temp.mkdir()
    monkeypatch.setattr(paths, "get_default_user_data_root", lambda: blocker)
    monkeypatch.setattr(paths.tempfile, "gettempdir", lambda: str(fake_temp))
    paths.reset_user_data_root_cache()

    root, source, note = paths.resolve_user_root()
    assert source == "fallback"
    assert root == (fake_temp / paths.APP_NAME / "userdata").resolve()
    assert note and "默认目录不可写" in note


def test_user_level_dirs_derived_from_root(tmp_path):
    root = paths.get_user_data_root()
    assert paths.get_data_dir("gallery") == root / "data" / "gallery"
    assert paths.get_config_dir("presets") == root / "config" / "presets"
    assert paths.get_cache_dir("marketplace") == root / "cache" / "marketplace"
    assert paths.get_log_dir("comfyui") == root / "logs" / "comfyui"
    assert paths.get_backup_dir() == root / "backup"
    assert paths.get_lora_data_dir() == root / "lora_data"
    assert paths.get_settings_file() == root / "config" / "settings.json"
    for path in (
        paths.get_data_dir("gallery"),
        paths.get_config_dir("presets"),
        paths.get_cache_dir("marketplace"),
        paths.get_log_dir("comfyui"),
        paths.get_backup_dir(),
        paths.get_lora_data_dir(),
    ):
        assert path.exists()


def test_system_level_paths_do_not_follow_user_root(tmp_path):
    assert paths.get_project_root() not in paths.get_user_data_root().parents
    assert paths.get_webview2_dir() == paths.get_machine_app_dir() / "webview2"
    assert paths.get_mingit_dir().is_relative_to(paths.get_project_root())


def test_write_and_clear_pointer(tmp_path):
    custom = tmp_path / "moving-root"
    pointer = paths.write_userdata_pointer(custom)
    assert pointer.read_text(encoding="utf-8") == str(custom.resolve())
    paths.clear_userdata_pointer()
    assert not pointer.exists()
    assert paths.get_user_data_source() == "default"


def test_legacy_candidates_point_to_install_root():
    candidates = dict(paths.get_legacy_userdata_candidates())
    assert candidates["data"] == paths.get_project_root() / "data"
    assert candidates["config"] == paths.get_project_root() / "backend" / "config"
    assert candidates["backup"] == paths.get_project_root() / "backup"
