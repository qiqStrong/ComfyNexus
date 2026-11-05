"""
路径管理工具模块（单一事实来源）

数据分层原则：
- **系统级数据**：随安装目录存在（dist/、backend/、MinGit、VERSION、default_config.json 等），
  删除项目目录即清空，只读或可由安装包重建。
- **用户级数据**：用户安装后产生的数据（资产库、提示词、工作流元数据、AI 对话、密钥、
  配置、备份、LoRA 扫描缓存等），保存在**机器级用户数据根**，换项目目录/换副本/重新 clone
  都能继续使用。

定位顺序（见 ``get_user_data_root``）：
1. 环境变量 ``COMFYUI_BOX_USERDATA``（绝对路径，便于测试/多实例）
2. 机器级指针文件 ``%LOCALAPPDATA%\\Comfyui-Box\\userdata.location``
3. 默认目录 ``%LOCALAPPDATA%\\Comfyui-Box\\userdata``

指针文件位于机器级目录而不是项目内，因此"项目内相对路径"不会把数据绑死在副本里。

Author: Comfyui-Box 开发团队
Date: 2026-02-09
"""

import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import List, Optional, Tuple

APP_NAME = "Comfyui-Box"
USERDATA_ENV_VAR = "COMFYUI_BOX_USERDATA"
USERDATA_POINTER_FILENAME = "userdata.location"
USERDATA_MARKER_FILENAME = ".initialized"
LEGACY_MARKER_FILENAME = ".migrated-from-userdata.json"
WIPE_REQUEST_FILENAME = ".wipe-request.json"

_resolve_lock = threading.RLock()
_resolved_root_cache: Optional[Path] = None


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_project_root() -> Path:
    """
    获取安装根目录（系统级）

    Returns:
        Path: 开发环境为 backend 的父目录；打包环境为 exe 所在目录

    说明：
        仅用于访问与安装包一起分发、随项目目录删除而清空的内容
        （dist/、backend/、MinGit、VERSION、comfyui_box_version.py 等）。
        用户级数据请使用 ``get_user_data_root`` 及其派生函数。
    """
    if _is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent.parent


def get_internal_dir() -> Path:
    """
    获取内部资源目录（打包环境专用，系统级）

    Returns:
        Path: 打包环境为 PyInstaller 解压目录（_internal / _MEIPASS），开发环境与安装根目录相同
    """
    if _is_frozen():
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent.parent


# ========== 用户数据根（机器级） ==========

def get_machine_app_dir() -> Path:
    """
    获取机器级应用目录（不属于用户数据根，存放指针与 WebView2 缓存）

    说明：
        Windows 优先 %LOCALAPPDATA%，缺失时退回 %APPDATA%，再退回 home。
        不使用项目内路径，保证同一台机器上任意一份副本都指向同一个位置。
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if not base:
            base = str(Path.home())
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def get_userdata_pointer_file() -> Path:
    """机器级指针文件路径（内容为用户数据根的绝对路径，一行纯文本）。"""
    return get_machine_app_dir() / USERDATA_POINTER_FILENAME


def get_default_user_data_root() -> Path:
    """默认用户数据根：%LOCALAPPDATA%\\Comfyui-Box\\userdata。"""
    return get_machine_app_dir() / "userdata"


def _is_writable_dir(path: Path) -> bool:
    """检查目录是否可写（必要时创建）。不会抛出异常。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path), prefix=".write-test.")
        os.close(fd)
        os.unlink(tmp_name)
        return True
    except OSError:
        return False


def _read_pointer() -> Optional[Path]:
    """读取指针文件；不存在/内容为空/格式无效时返回 None。"""
    try:
        raw = get_userdata_pointer_file().read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, UnicodeError):
        return None
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else None


def write_userdata_pointer(root: Path) -> Path:
    """
    原子写入机器级指针文件。

    Args:
        root: 用户数据根绝对路径

    Returns:
        Path: 指针文件路径
    """
    root = Path(root).resolve()
    pointer = get_userdata_pointer_file()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(pointer.parent), prefix=".userdata.loc.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(str(root))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, pointer)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return pointer


def clear_userdata_pointer() -> None:
    """删除机器级指针文件（恢复默认目录）。"""
    try:
        get_userdata_pointer_file().unlink()
    except FileNotFoundError:
        pass
    _reset_root_cache()


def _reset_root_cache() -> None:
    global _resolved_root_cache
    with _resolve_lock:
        _resolved_root_cache = None


def reset_user_data_root_cache() -> None:
    """清除已解析的用户数据根缓存（更改指针/环境变量后调用，随后需重启应用）。"""
    _reset_root_cache()


def get_user_data_root() -> Path:
    """
    获取用户数据根（机器级、可迁移、可清理）。

    Returns:
        Path: 用户数据根绝对路径（已确保可写）

    解析优先级：
        1. 环境变量 ``COMFYUI_BOX_USERDATA``（绝对路径）
        2. 指针文件 ``%LOCALAPPDATA%\\Comfyui-Box\\userdata.location``
        3. 默认 ``%LOCALAPPDATA%\\Comfyui-Box\\userdata``

    若指针/环境变量指向的目录不可写（例如移动硬盘拔掉），降级到默认目录并记录告警；
    不会静默覆盖指针文件。
    """
    global _resolved_root_cache
    with _resolve_lock:
        if _resolved_root_cache is not None:
            return _resolved_root_cache

        default_root = get_default_user_data_root()
        candidates: List[Path] = []

        env_value = os.environ.get(USERDATA_ENV_VAR, "").strip()
        env_root: Optional[Path] = None
        if env_value:
            env_root = Path(env_value)
            if env_root.is_absolute():
                candidates.append(env_root)

        pointer_root = _read_pointer()
        if pointer_root is not None and pointer_root not in candidates:
            candidates.append(pointer_root)

        candidates.append(default_root)

        for candidate in candidates:
            if _is_writable_dir(candidate):
                _resolved_root_cache = candidate.resolve()
                return _resolved_root_cache

        # 兜底：临时目录下建一个可写根，避免直接崩溃（理论上极少发生）
        fallback = Path(tempfile.gettempdir()) / APP_NAME / "userdata"
        fallback.mkdir(parents=True, exist_ok=True)
        _resolved_root_cache = fallback
        return _resolved_root_cache


def get_user_data_source() -> str:
    """返回当前用户数据根的来源：env / pointer / default / fallback。"""
    env_value = os.environ.get(USERDATA_ENV_VAR, "").strip()
    if env_value and Path(env_value).is_absolute():
        return "env"
    pointer_root = _read_pointer()
    if pointer_root is not None:
        return "pointer" if pointer_root == get_user_data_root() else "pointer-invalid"
    if get_user_data_root() == get_default_user_data_root():
        return "default"
    return "fallback"


def get_userdata_marker_file(root: Optional[Path] = None) -> Path:
    """首启完成标记文件（存在即表示用户已确认数据目录）。"""
    return Path(root) / USERDATA_MARKER_FILENAME if root else get_user_data_root() / USERDATA_MARKER_FILENAME


def is_user_data_initialized(root: Optional[Path] = None) -> bool:
    """判断用户数据目录是否已完成首启初始化。"""
    return get_userdata_marker_file(root).exists()


def mark_user_data_initialized(root: Optional[Path] = None, extra: Optional[dict] = None) -> Path:
    """写入首启完成标记（JSON 文本，便于排障）。"""
    marker = get_userdata_marker_file(root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {"initialized_at": __import__("datetime").datetime.now().isoformat(timespec="seconds")}
    if extra:
        payload.update(extra)
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return marker


# ========== 用户级目录（全部派生自用户数据根） ==========

def get_data_dir(subdir: Optional[str] = None) -> Path:
    """
    获取业务数据目录（用户级）

    Args:
        subdir: 子目录名称（可选）

    Returns:
        Path: <用户数据根>/data[/subdir]
    """
    data_dir = get_user_data_root() / "data"
    if subdir:
        data_dir = data_dir / subdir
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_config_dir(subdir: Optional[str] = None) -> Path:
    """
    获取配置目录（用户级）

    Args:
        subdir: 子目录名称（可选，可含 / 分隔的多级路径）

    Returns:
        Path: <用户数据根>/config[/subdir]
    """
    config_dir = get_user_data_root() / "config"
    if subdir:
        config_dir = config_dir / subdir
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_cache_dir(subdir: Optional[str] = None) -> Path:
    """
    获取缓存目录（用户级，可安全清理，删除后自动重建）

    Returns:
        Path: <用户数据根>/cache[/subdir]
    """
    cache_dir = get_user_data_root() / "cache"
    if subdir:
        cache_dir = cache_dir / subdir
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_log_dir(subdir: Optional[str] = None) -> Path:
    """
    获取日志目录（用户级诊断产物，可清理）

    Returns:
        Path: <用户数据根>/logs[/subdir]
    """
    log_dir = get_user_data_root() / "logs"
    if subdir:
        log_dir = log_dir / subdir
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_backup_dir(subdir: Optional[str] = None) -> Path:
    """
    获取救援快照备份目录（用户级业务数据，迁移时必须一起搬）

    Returns:
        Path: <用户数据根>/backup[/subdir]
    """
    backup_dir = get_user_data_root() / "backup"
    if subdir:
        backup_dir = backup_dir / subdir
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def get_lora_data_dir(subdir: Optional[str] = None) -> Path:
    """
    获取 LoRA 扫描数据目录（扫描结果 + 预览图缓存，可重建）

    Returns:
        Path: <用户数据根>/lora_data[/subdir]
    """
    lora_dir = get_user_data_root() / "lora_data"
    if subdir:
        lora_dir = lora_dir / subdir
    lora_dir.mkdir(parents=True, exist_ok=True)
    return lora_dir


def get_update_cache_dir() -> Path:
    """获取更新缓存目录（用户级缓存，可清理）。"""
    update_cache_dir = get_cache_dir("updates")
    update_cache_dir.mkdir(parents=True, exist_ok=True)
    return update_cache_dir


def get_user_data_dir() -> Path:
    """
    兼容旧名称：返回用户数据根（历史上曾返回 %APPDATA%/Comfyui-Box）。

    新代码请直接使用 ``get_user_data_root``。
    """
    return get_user_data_root()


# ========== 系统级路径（随安装目录存在） ==========

def get_version_file() -> Path:
    """获取版本文件路径（系统级：安装包内 comfyui_box_version.py）。"""
    if _is_frozen():
        return get_internal_dir() / "comfyui_box_version.py"
    return get_project_root() / "comfyui_box_version.py"


def get_dev_update_source_file() -> Path:
    """获取开发模式更新源文件（系统级 dev 文件）。"""
    return get_project_root() / "dev"


def get_settings_file() -> Path:
    """获取 settings.json 文件路径（用户级配置）。"""
    return get_config_dir() / "settings.json"


def get_default_config_file() -> Path:
    """
    获取 default_config.json 文件路径（系统级随包默认配置）

    说明：
        该文件是安装包自带的只读默认值；用户配置写在 ``get_config_dir()``。
        打包时未随包分发该文件则返回用户配置目录下的同名路径（调用方按"不存在"处理）。
    """
    if _is_frozen():
        for candidate in (
            get_internal_dir() / "backend" / "config" / "default_config.json",
            get_project_root() / "backend" / "config" / "default_config.json",
        ):
            if candidate.exists():
                return candidate
    else:
        shipped = get_project_root() / "backend" / "config" / "default_config.json"
        if shipped.exists():
            return shipped
    return get_config_dir() / "default_config.json"


def get_database_file(db_name: str = "ai_assistant.db") -> Path:
    """获取数据库文件路径（用户级业务数据）。"""
    return get_data_dir() / db_name


def get_prompt_data_dir(subdir: Optional[str] = None) -> Path:
    """获取提示词库数据目录（用户级业务数据）。"""
    prompt_dir = get_data_dir() / "prompt"
    if subdir:
        prompt_dir = prompt_dir / subdir
    prompt_dir.mkdir(parents=True, exist_ok=True)
    return prompt_dir


def get_prompt_images_dir() -> Path:
    """获取提示词库图片存储目录（用户级业务数据）。"""
    return get_prompt_data_dir("images")


def get_tools_dir(subdir: Optional[str] = None) -> Path:
    """
    获取外部工具目录（系统级）

    说明：
        开发环境为 <安装根>/backend/，打包环境为 <安装根>/tools/。
        工具随安装包分发，不属于用户数据。
    """
    if _is_frozen():
        tools_dir = get_project_root() / "tools"
    else:
        tools_dir = get_project_root() / "backend"
    if subdir:
        tools_dir = tools_dir / subdir
    return tools_dir


def get_mingit_dir() -> Path:
    """获取 MinGit 目录（系统级，不自动创建）。"""
    if _is_frozen():
        return get_project_root() / "tools" / "mingit"
    return get_project_root() / "backend" / "MinGit-2.53.0-64-bit"


def get_old_mingit_dirs() -> list[Path]:
    """获取旧版 MinGit 可能存在的目录列表（打包环境迁移检测用）。"""
    old_dirs = []
    if _is_frozen():
        internal_dir = get_internal_dir()
        old_patterns = [
            "MinGit-2.53.0-64-bit",
            "MinGit-2.52.0-64-bit",
            "MinGit-2.51.0-64-bit",
        ]
        for pattern in old_patterns:
            old_path = internal_dir / "backend" / pattern
            if old_path.exists():
                old_dirs.append(old_path)
    return old_dirs


def get_nsfw_model_path() -> Path:
    """获取 NSFW 分类模型路径（系统级随包资源）。"""
    if _is_frozen():
        return get_internal_dir() / "models" / "nsfw.onnx"
    return get_project_root() / "backend" / "models" / "nsfw.onnx"


def get_webview2_dir() -> Path:
    """
    获取 WebView2 用户数据目录（机器级缓存）

    说明：
        固定在 %LOCALAPPDATA%\\Comfyui-Box\\webview2，避免用户数据根含中文导致
        WebView2 初始化异常；属于可清理缓存，不随用户数据迁移。
    """
    return get_machine_app_dir() / "webview2"


def get_legacy_userdata_candidates() -> List[Tuple[str, Path]]:
    """
    获取旧版布局中可能存放用户数据的目录（用于首启检测与迁移提示）

    Returns:
        list[(kind, path)]，kind ∈ {"data", "config", "backup", "lora_data"}
    """
    project_root = get_project_root()
    candidates: List[Tuple[str, Path]] = [
        ("data", project_root / "data"),
        ("backup", project_root / "backup"),
        ("lora_data", project_root / "lora_data"),
    ]
    # 打包环境旧配置在 exe 同级 config/；开发环境在 backend/config/
    if _is_frozen():
        candidates.append(("config", project_root / "config"))
    else:
        candidates.append(("config", project_root / "backend" / "config"))
    return candidates


# 便捷常量（向后兼容；首次 import 时解析，运行期改指针需重启）
PROJECT_ROOT = get_project_root()
INTERNAL_DIR = get_internal_dir()
USER_DATA_ROOT = get_user_data_root()
DATA_DIR = get_data_dir()
CACHE_DIR = get_cache_dir()
LOG_DIR = get_log_dir()
CONFIG_DIR = get_config_dir()
PROMPT_DATA_DIR = get_prompt_data_dir()
PROMPT_IMAGES_DIR = get_prompt_images_dir()
TOOLS_DIR = get_tools_dir()
MINGIT_DIR = get_mingit_dir()


if __name__ == "__main__":
    print("=" * 60)
    print("路径管理工具测试")
    print("=" * 60)
    print(f"安装根目录（系统级）: {get_project_root()}")
    print(f"内部资源目录: {get_internal_dir()}")
    print(f"用户数据根: {get_user_data_root()} (来源: {get_user_data_source()})")
    print(f"用户数据已初始化: {is_user_data_initialized()}")
    print(f"业务数据目录: {get_data_dir()}")
    print(f"配置目录: {get_config_dir()}")
    print(f"缓存目录: {get_cache_dir()}")
    print(f"日志目录: {get_log_dir()}")
    print(f"备份目录: {get_backup_dir()}")
    print(f"LoRA 数据目录: {get_lora_data_dir()}")
    print(f"WebView2 数据目录: {get_webview2_dir()}")
    print("=" * 60)
    print(f"版本文件: {get_version_file()}")
    print(f"设置文件: {get_settings_file()}")
    print(f"默认配置: {get_default_config_file()}")
    print("=" * 60)
    print("旧布局候选:")
    for kind, path in get_legacy_userdata_candidates():
        print(f"  - [{kind}] {path} 存在={path.exists()}")
