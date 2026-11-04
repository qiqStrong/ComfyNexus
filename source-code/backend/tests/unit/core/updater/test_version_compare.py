"""版本比较的最小单测：确保大小写与前缀不影响判定。"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[4]
_SOURCE_ROOT = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR), str(_SOURCE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.src.core.updater.update_checker import UpdateChecker  # noqa: E402


def compare(current, latest):
    """_compare_versions 不依赖实例状态，直接以未绑定方式调用。"""
    return UpdateChecker._compare_versions(None, current, latest)


def test_same_version_ignores_case_and_prefix():
    assert compare("V1.0.0", "v1.0.0") == 0
    assert compare("V1.0.0", "1.0.0") == 0
    assert compare(" V1.0.0 ", "v1.0.0") == 0


def test_newer_version():
    assert compare("V1.0.0", "V1.0.1") == -1
    assert compare("V1.0.1", "V1.0.0") == 1


def test_older_version():
    assert compare("V1.0.0", "V0.9.4") == 1
    assert compare("V0.9.4", "V1.0.0") == -1


def test_rc_is_lower_than_stable():
    assert compare("RC_1.0.0", "V1.0.0") == -1
    assert compare("V1.0.0", "RC_1.0.0") == 1


def test_unparseable_falls_back_without_raising():
    assert compare("dev", "dev") == 0
    assert compare("", "") == 0
    assert compare("abc", "abd") == -1
    assert compare("V1.0.0", "V1.0.0-beta") == 0
