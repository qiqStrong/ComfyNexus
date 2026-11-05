"""
用户数据层管理测试

覆盖：一键迁移（计数/密钥校验/源目录只读）、失败回滚、缓存清理、业务数据清空。
"""

import json
import sqlite3
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_SOURCE_ROOT = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR), str(_SOURCE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402

from backend.src.core.userdata import manager  # noqa: E402
from backend.src.utils import paths  # noqa: E402


@pytest.fixture
def user_root(monkeypatch, tmp_path):
    """测试注入：把当前进程的数据根固定到临时目录（不依赖环境变量）。"""
    root = (tmp_path / "userdata").resolve()
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths, "get_user_data_root", lambda override=None: root)
    monkeypatch.setattr(paths, "get_user_data_source", lambda override=None: "override")
    monkeypatch.setattr(paths, "get_user_data_resolution_note", lambda override=None: None)
    monkeypatch.setattr(manager, "_PROCESS_START_ROOT", None)
    yield root
    manager._PROCESS_START_ROOT = None


def _create_legacy_root(root: Path, with_key: bool = True) -> Path:
    """构造旧布局样本：data/ + backend/config/，含资产/缩略图/提示词/工作流/对话/密钥。"""
    data = root / "data"
    (data / "gallery" / "thumbnails").mkdir(parents=True)
    (data / "prompt" / "images").mkdir(parents=True)
    (data / "workflows").mkdir(parents=True)
    (data / "secrets").mkdir(parents=True)
    config = root / "backend" / "config" / "presets" / "geek"
    config.mkdir(parents=True)

    (data / "gallery" / "assets.json").write_text(json.dumps({
        "assets": [{"id": f"a{i}"} for i in range(3)],
        "categories": [{"id": "c1"}, {"id": "c2"}],
    }, ensure_ascii=False), encoding="utf-8")
    for i in range(2):
        (data / "gallery" / "thumbnails" / f"{i}.webp").write_bytes(b"thumb")
    for i in range(2):
        (data / "prompt" / "images" / f"{i}.png").write_bytes(b"png")
    (data / "prompt" / "prompts.json").write_text('{"prompts": []}', encoding="utf-8")
    (data / "workflows" / "w1.json").write_text("{}", encoding="utf-8")
    (root / "backend" / "config" / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
    (config / "g1.json").write_text("{}", encoding="utf-8")

    key = Fernet.generate_key()
    if with_key:
        (data / "secrets" / "ai_fernet.key").write_bytes(key)

    conn = sqlite3.connect(data / "ai_assistant.db")
    try:
        conn.execute("CREATE TABLE topics (id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO topics (id) VALUES (?)", [(1,), (2,)])
        conn.execute("CREATE TABLE api_configs (id INTEGER PRIMARY KEY, api_key TEXT)")
        token = Fernet(key).encrypt(b"sk-test").decode("utf-8")
        conn.execute("INSERT INTO api_configs (api_key) VALUES (?)", (f"encrypted:{token}",))
        conn.commit()
    finally:
        conn.close()
    return root


def test_migrate_counts_and_key_roundtrip(user_root):
    source = _create_legacy_root(user_root.parent / "legacy-install")
    result = manager._migrate_blocking(source, user_root)

    assert result["success"] is True
    assert result["dest_counts"]["assets"] == 3
    assert result["dest_counts"]["categories"] == 2
    assert result["dest_counts"]["thumbnails"] == 2
    assert result["dest_counts"]["prompt_images"] == 2
    assert result["dest_counts"]["workflows_files"] == 1
    assert result["dest_counts"]["db_topics"] == 2
    assert result["key_verification"]["encrypted_keys"] == 1
    assert result["key_verification"]["decrypted"] == 1
    assert result["key_verification"]["failed"] == 0

    # 源目录只读：文件仍在，且没有被写入迁移标记
    assert (source / "data" / "secrets" / "ai_fernet.key").exists()
    assert not (source / paths.LEGACY_MARKER_FILENAME).exists()
    assert (user_root / paths.LEGACY_MARKER_FILENAME).exists()


def test_migrate_idempotent_on_existing_target(user_root):
    source = _create_legacy_root(user_root.parent / "legacy-install")
    assert manager._migrate_blocking(source, user_root)["success"] is True
    second = manager._migrate_blocking(source, user_root)
    assert second["success"] is True
    assert manager.collect_counts(user_root)["assets"] == 3
    assert manager.collect_counts(user_root)["db_topics"] == 2


def test_migrate_rolls_back_when_copy_fails(user_root, monkeypatch):
    source = _create_legacy_root(user_root.parent / "legacy-install")

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(manager.shutil, "copy2", _boom)
    result = manager._migrate_blocking(source, user_root)

    assert result["success"] is False
    assert "disk full" in result["error"]
    # 目标目录没有被写入业务文件，暂存目录也已清理
    assert not list((user_root / "data").rglob("*")) if (user_root / "data").exists() else True
    assert not list(user_root.glob(".migrating-*"))


def test_migrate_fails_when_encryption_key_missing(user_root):
    source = _create_legacy_root(user_root.parent / "legacy-install", with_key=False)
    result = manager._migrate_blocking(source, user_root)

    assert result["success"] is False
    assert "密钥" in result["error"]
    assert manager.collect_counts(user_root)["assets"] == 0


def test_migration_to_new_root_writes_pointer(user_root, monkeypatch, tmp_path):
    """迁移到新目录成功时必须写机器级指针，且当前进程不切换数据根。"""
    source = _create_legacy_root(tmp_path / "legacy-install")
    target = (tmp_path / "new-root").resolve()
    pointer_file = tmp_path / "machine" / "userdata.location"
    monkeypatch.setattr(paths, "get_userdata_pointer_file", lambda: pointer_file)

    started = manager.start_migration(str(source), str(target))
    assert started["success"] is True
    for _ in range(100):
        state = manager.get_migration_status()
        if not state["running"]:
            break
        __import__("time").sleep(0.05)

    result = state["result"]
    assert result["success"] is True
    assert result["restart_required"] is True
    assert pointer_file.read_text(encoding="utf-8") == str(target)
    # 当前进程仍使用旧根，等待重启
    assert paths.get_user_data_root() == user_root
    assert manager.collect_counts(target)["assets"] == 3


def test_inspect_root_reports_existing_business_data(user_root):
    (user_root / "data" / "gallery").mkdir(parents=True, exist_ok=True)
    (user_root / "data" / "gallery" / "assets.json").write_text(
        '{"assets": [{"id": "a"}], "categories": [{"id": "c"}]}', encoding="utf-8"
    )
    info = manager.inspect_user_data_root(str(user_root))
    assert info["success"] is True
    assert info["has_business"] is True
    assert info["counts"]["assets"] == 1


def test_clean_cache_and_logs(user_root):
    cache = user_root / "cache"
    logs = user_root / "logs"
    (cache / "marketplace").mkdir(parents=True)
    (cache / "marketplace" / "plugins.json").write_text("{}", encoding="utf-8")
    logs.mkdir(parents=True)
    (logs / "app.log").write_text("line", encoding="utf-8")

    result = manager.clean_cache_and_logs(["cache", "logs"])

    assert result["success"] is True
    assert not list(cache.iterdir())
    assert not list(logs.iterdir())


def test_business_wipe_applies_on_next_start(user_root):
    data_file = user_root / "data" / "gallery" / "assets.json"
    data_file.parent.mkdir(parents=True)
    data_file.write_text('{"assets": [{"id": "x"}]}', encoding="utf-8")
    (user_root / "config").mkdir(parents=True, exist_ok=True)
    (user_root / "config" / "settings.json").write_text("{}", encoding="utf-8")

    queued = manager.request_business_wipe()
    assert queued["restart_required"] is True
    assert (user_root / paths.WIPE_REQUEST_FILENAME).exists()

    applied = manager.apply_pending_wipe()

    assert applied["applied"] is True
    assert not data_file.exists()
    assert not (user_root / "config" / "settings.json").exists()
    assert not (user_root / paths.WIPE_REQUEST_FILENAME).exists()
    assert manager.collect_counts(user_root)["assets"] == 0
