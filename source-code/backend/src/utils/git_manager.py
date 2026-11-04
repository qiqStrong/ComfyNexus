"""
Git 管理器模块

提供统一的 Git 可执行文件管理，支持：
- MinGit（内置）
- 系统 Git
- 自定义 Git 路径
- 旧版本 MinGit 迁移
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum

from backend.src.utils.paths import (
    get_project_root,
    get_internal_dir,
    get_mingit_dir,
    get_old_mingit_dirs,
)
from backend.src.utils.logger import app_logger as logger


class GitMode(Enum):
    MINGIT = "mingit"
    SYSTEM = "system"
    CUSTOM = "custom"


@dataclass
class GitStatus:
    available: bool
    mode: GitMode
    path: str
    version: str
    message: str
    needs_setup: bool
    # Git 来源：bundled（内置 MinGit）/ system（系统 Git）/ custom（自定义）/""
    source: str = ""


class GitManager:
    """
    Git 管理器
    
    负责管理 Git 可执行文件的获取、验证、迁移和环境配置。
    """
    
    MINGIT_VERSION = "2.53.0"
    MIN_GIT_VERSION = "2.30.0"
    
    def __init__(self, settings_manager=None):
        """
        初始化 Git 管理器
        
        Args:
            settings_manager: 设置管理器实例（可选）
        """
        self._settings_manager = settings_manager
        self._git_executable: Optional[str] = None
        self._git_version: Optional[str] = None
    
    @property
    def settings_manager(self):
        """延迟加载设置管理器"""
        if self._settings_manager is None:
            from backend.src.core.settings_manager import SettingsManager
            self._settings_manager = SettingsManager()
        return self._settings_manager
    
    def check_availability(self) -> GitStatus:
        """
        检查 Git 可用性
        
        Returns:
            GitStatus: Git 状态信息
        """
        git_mode = self.settings_manager.get_git_mode()
        
        if git_mode == GitMode.CUSTOM.value:
            return self._check_custom_git()
        elif git_mode == GitMode.SYSTEM.value:
            return self._check_system_git()
        else:
            return self._check_mingit()
    
    def _check_mingit(self) -> GitStatus:
        """
        检查 MinGit 可用性

        解析顺序：内置 MinGit → 系统 Git → 可用性否决。
        内置 MinGit 缺失或损坏但系统 Git 可用时，回退到系统 Git，
        避免新机器首次启动被误判为“Git 不可用”而弹出引导窗。
        """
        mingit_dir = get_mingit_dir()
        git_exe = mingit_dir / "cmd" / "git.exe"
        mingit_error = ""
        
        if git_exe.exists():
            success, version = self._verify_git_executable(str(git_exe))
            if success:
                return GitStatus(
                    available=True,
                    mode=GitMode.MINGIT,
                    path=str(git_exe),
                    version=version,
                    message="MinGit 可用",
                    needs_setup=False,
                    source="bundled"
                )
            mingit_error = f"MinGit 存在但无法执行: {version}"
        
        system_status = self._check_system_git()
        if system_status.available:
            logger.info(f"[GitManager] 内置 MinGit 不可用，回退使用系统 Git: {system_status.path}")
            return GitStatus(
                available=True,
                mode=GitMode.SYSTEM,
                path=system_status.path,
                version=system_status.version,
                message="内置 MinGit 不可用，已回退使用系统 Git",
                needs_setup=False,
                source="system"
            )
        
        return GitStatus(
            available=False,
            mode=GitMode.MINGIT,
            path=str(git_exe) if git_exe.exists() else "",
            version="",
            message=mingit_error or "未检测到 Git，需要下载 MinGit 或指定 Git 路径",
            needs_setup=True,
            source=""
        )
    
    def _check_system_git(self) -> GitStatus:
        """检查系统 Git 可用性"""
        success, version = self._verify_git_executable("git")
        
        if success:
            git_path = self._find_system_git_path()
            return GitStatus(
                available=True,
                mode=GitMode.SYSTEM,
                path=git_path or "git",
                version=version,
                message="系统 Git 可用",
                needs_setup=False,
                source="system"
            )
        
        return GitStatus(
            available=False,
            mode=GitMode.SYSTEM,
            path="",
            version="",
            message="系统 Git 不可用",
            needs_setup=True
        )
    
    def _check_custom_git(self) -> GitStatus:
        """检查自定义 Git 可用性"""
        custom_path = self.settings_manager.get_custom_git_path()
        
        if not custom_path:
            return GitStatus(
                available=False,
                mode=GitMode.CUSTOM,
                path="",
                version="",
                message="未配置自定义 Git 路径",
                needs_setup=True
            )
        
        if not Path(custom_path).exists():
            return GitStatus(
                available=False,
                mode=GitMode.CUSTOM,
                path=custom_path,
                version="",
                message=f"自定义 Git 路径不存在: {custom_path}",
                needs_setup=True
            )
        
        success, version = self._verify_git_executable(custom_path)
        if success:
            return GitStatus(
                available=True,
                mode=GitMode.CUSTOM,
                path=custom_path,
                version=version,
                message="自定义 Git 可用",
                needs_setup=False,
                source="custom"
            )
        
        return GitStatus(
            available=False,
            mode=GitMode.CUSTOM,
            path=custom_path,
            version="",
            message=f"自定义 Git 无法执行: {version}",
            needs_setup=True
        )
    
    def _verify_git_executable(self, git_path: str) -> tuple[bool, str]:
        """
        验证 Git 可执行文件
        
        Args:
            git_path: Git 可执行文件路径
            
        Returns:
            tuple[bool, str]: (是否成功, 版本号或错误信息)
        """
        try:
            result = subprocess.run(
                [git_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            
            if result.returncode == 0:
                version_output = result.stdout.strip()
                if "git version" in version_output:
                    version = version_output.replace("git version", "").strip()
                    return True, version
                return True, version_output
            
            return False, f"退出码: {result.returncode}"
            
        except subprocess.TimeoutExpired:
            return False, "执行超时"
        except FileNotFoundError:
            return False, "文件未找到"
        except Exception as e:
            return False, str(e)
    
    def _find_system_git_path(self) -> Optional[str]:
        """查找系统 Git 的完整路径"""
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["where", "git"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    paths = result.stdout.strip().split("\n")
                    if paths:
                        return paths[0].strip()
            else:
                result = subprocess.run(
                    ["which", "git"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return result.stdout.strip()
        except Exception:
            pass
        
        return None
    
    def get_git_executable(self) -> str:
        """
        获取 Git 可执行文件路径
        
        Returns:
            str: Git 可执行文件路径
        """
        if self._git_executable:
            return self._git_executable
        
        status = self.check_availability()
        
        if status.available:
            self._git_executable = status.path
            self._git_version = status.version
            return status.path
        
        return "git"
    
    def clear_cache(self):
        """
        清除 Git 路径缓存
        
        当用户更改 Git 设置后调用此方法，强制下次调用时重新获取 Git 路径。
        """
        self._git_executable = None
        self._git_version = None
        logger.debug("[GitManager] Git 路径缓存已清除")
    
    def setup_environment(self):
        """
        设置 Git 环境变量
        
        将 MinGit 的路径添加到 PATH 环境变量的最前面，
        确保所有 Git 调用都使用指定的 Git 版本。
        同时注入 GitHub 镜像加速的环境变量配置。
        """
        git_mode = self.settings_manager.get_git_mode()
        
        if git_mode != GitMode.MINGIT.value:
            self._setup_mirror_env()
            return
        
        mingit_dir = get_mingit_dir()
        mingit_cmd_dir = mingit_dir / "cmd"
        mingit_bin_dir = mingit_dir / "mingw64" / "bin"
        
        if not mingit_cmd_dir.exists():
            self._setup_mirror_env()
            return
        
        current_path = os.environ.get("PATH", "")
        mingit_paths = [str(mingit_cmd_dir), str(mingit_bin_dir)]
        
        path_list = current_path.split(os.pathsep)
        mingit_paths_to_add = [p for p in mingit_paths if p not in path_list]
        
        if mingit_paths_to_add:
            new_path = os.pathsep.join(mingit_paths_to_add + path_list)
            os.environ["PATH"] = new_path
        
        self._clear_invalid_credential_helper()
        self._setup_mirror_env()
    
    def _setup_mirror_env(self):
        """
        设置 GitHub 镜像加速的环境变量
        
        通过 GIT_CONFIG_* 环境变量注入镜像配置，
        不修改磁盘配置文件，仅影响当前进程。
        """
        try:
            from backend.src.utils.github_mirror import github_mirror_manager
            
            if not github_mirror_manager.is_enabled():
                return
            
            mirror = github_mirror_manager.get_mirror_for_type("github")
            if mirror:
                os.environ["GIT_CONFIG_COUNT"] = "1"
                os.environ["GIT_CONFIG_KEY_0"] = f"url.https://{mirror}/.insteadOf"
                os.environ["GIT_CONFIG_VALUE_0"] = "https://github.com/"
                logger.info(f"[GitManager] 已注入 GitHub 镜像环境变量: {mirror}")
            
            settings = github_mirror_manager._load_settings()
            if not settings.get("verifySSL", True):
                os.environ["GIT_SSL_NO_VERIFY"] = "true"
        except Exception as e:
            logger.debug(f"[GitManager] 设置镜像环境变量失败（可忽略）: {e}")
    
    def _clear_invalid_credential_helper(self):
        """
        清除 MinGit 系统配置中无效的 credential.helper = manager
        
        MinGit 自带的 etc/gitconfig 可能配置了 credential.helper = manager，
        但 MinGit 不包含 git-credential-manager.exe，导致 Git 弹出交互式登录窗口。
        此方法在 setup_environment 中自动调用，清除该无效配置。
        """
        try:
            git_exe = self.get_git_executable()
            if not git_exe:
                return
            
            result = subprocess.run(
                [git_exe, "config", "--system", "--get", "credential.helper"],
                capture_output=True, text=True, timeout=5,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            
            if result.returncode == 0 and result.stdout.strip() == "manager":
                logger.info("[GitManager] 检测到 MinGit 无效的 credential.helper=manager，正在清除...")
                subprocess.run(
                    [git_exe, "config", "--system", "--unset", "credential.helper"],
                    capture_output=True, text=True, timeout=5,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                logger.info("[GitManager] 已清除无效的 credential.helper 配置")
        except Exception as e:
            logger.debug(f"[GitManager] 清除 credential.helper 时出错（可忽略）: {e}")
    
    def migrate_from_old_location(self) -> tuple[bool, str]:
        """
        从旧位置迁移 MinGit
        
        Returns:
            tuple[bool, str]: (是否迁移成功, 消息)
        """
        if not getattr(sys, 'frozen', False):
            return True, "开发环境无需迁移"
        
        migration_marker = get_project_root() / ".mingit_migrated"
        if migration_marker.exists():
            return True, "MinGit 已迁移"
        
        new_mingit_dir = get_mingit_dir()
        if new_mingit_dir.exists() and (new_mingit_dir / "cmd" / "git.exe").exists():
            migration_marker.touch()
            return True, "MinGit 已存在"
        
        old_mingit_dirs = get_old_mingit_dirs()
        if not old_mingit_dirs:
            return True, "未发现旧版 MinGit"
        
        old_mingit_dir = old_mingit_dirs[0]
        
        try:
            new_mingit_dir.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.move(str(old_mingit_dir), str(new_mingit_dir))
            
            git_exe = new_mingit_dir / "cmd" / "git.exe"
            if git_exe.exists():
                migration_marker.touch()
                return True, f"MinGit 迁移成功: {old_mingit_dir.name} -> {new_mingit_dir}"
            else:
                return False, "迁移后 git.exe 不存在"
                
        except Exception as e:
            return False, f"迁移失败: {str(e)}"
    
    def set_custom_git_path(self, path: str) -> tuple[bool, str]:
        """
        设置自定义 Git 路径
        
        Args:
            path: git.exe 的完整路径
            
        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        path_obj = Path(path)
        
        if not path_obj.exists():
            return False, f"路径不存在: {path}"
        
        if path_obj.name.lower() != "git.exe":
            return False, "请选择 git.exe 文件"
        
        success, version = self._verify_git_executable(path)
        if not success:
            return False, f"Git 验证失败: {version}"
        
        result = self.settings_manager.set_custom_git_path(path)
        
        if result.get("success"):
            self._git_executable = path
            self._git_version = version
            return True, f"已设置自定义 Git: {version}"
        
        return False, result.get("message", "保存配置失败")
    
    def use_system_git(self) -> tuple[bool, str]:
        """
        使用系统 Git
        
        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        status = self._check_system_git()
        
        if not status.available:
            return False, "系统 Git 不可用"
        
        result = self.settings_manager.set_git_mode(GitMode.SYSTEM.value)
        
        if result.get("success"):
            self._git_executable = status.path
            self._git_version = status.version
            return True, f"已使用系统 Git: {status.version}"
        
        return False, result.get("message", "保存配置失败")
    
    def use_mingit(self) -> tuple[bool, str]:
        """
        使用 MinGit
        
        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        status = self._check_mingit()
        
        if not status.available:
            return False, "MinGit 不可用，请先下载"
        
        result = self.settings_manager.set_git_mode(GitMode.MINGIT.value)
        
        if result.get("success"):
            self._git_executable = status.path
            self._git_version = status.version
            return True, f"已使用 MinGit: {status.version}"
        
        return False, result.get("message", "保存配置失败")


git_manager = GitManager()


def get_git_executable() -> str:
    """
    获取 Git 可执行文件路径（兼容旧接口）
    
    Returns:
        str: Git 可执行文件路径
    """
    return git_manager.get_git_executable()


def setup_git_environment():
    """
    设置 Git 环境变量（兼容旧接口）
    """
    git_manager.setup_environment()


GIT_EXECUTABLE = get_git_executable()
