"""
GitHub 镜像源管理模块

提供 GitHub 资源访问的镜像加速功能，包括：
- URL 转换（Raw/Release/API）
- Git 环境变量注入
- 自动调度与故障转移
- 心跳检测
- 测速功能
- 防抖动策略
"""

import os
import subprocess
import time
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple, Callable, List
from datetime import datetime

import requests

from backend.src.utils.logger import app_logger as logger


MIRROR_PRESETS = {
    "hybrid": {
        "name": "混合加速",
        "description": "系统自动选择最优镜像",
        "github": "gitclone.com",
        "raw": "ghproxy.net",
        "api": None,
        "release": "ghproxy.net",
        "fallback": {
            "github": ["mirror.ghproxy.com", "ghproxy.net", None],
            "raw": ["gh.xxooo.cf", "fastgit.cc"],
            "release": ["fastgit.cc", "gh.xxooo.cf"],
        },
    },
    "gitclone": {
        "name": "GitClone + GHProxy",
        "description": "Git Clone 用 GitClone，文件下载用 GHProxy",
        "github": "gitclone.com",
        "raw": "ghproxy.net",
        "api": None,
        "release": "ghproxy.net",
        "fallback": {
            "github": ["mirror.ghproxy.com", "ghproxy.net", None],
            "release": ["fastgit.cc"],
        },
    },
    "ur1fun": {
        "name": "UR1Fun + GHProxy",
        "description": "Git Clone 用 UR1Fun，文件下载用 GHProxy",
        "github": "github.ur1.fun",
        "raw": "ghproxy.net",
        "api": None,
        "release": "ghproxy.net",
        "fallback": {
            "github": ["gitclone.com", "mirror.ghproxy.com", "ghproxy.net", None],
            "release": ["fastgit.cc"],
        },
    },
    "ghproxy": {
        "name": "GHProxy 纯加速",
        "description": "仅加速文件下载",
        "github": None,
        "raw": "ghproxy.net",
        "api": None,
        "release": "ghproxy.net",
        "fallback": {
            "github": ["mirror.ghproxy.com", None],
            "raw": ["gh.xxooo.cf"],
            "release": ["fastgit.cc"],
        },
    },
}

MIRROR_USER_AGENTS = {
    "ghproxy.net": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "mirror.ghproxy.com": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "gitclone.com": "git/2.0",
    "github.ur1.fun": "git/2.0",
    "fastgit.cc": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "gh.xxooo.cf": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

SPEED_TEST_FILES = {
    "github": "https://github.com/git/git/raw/master/README.md",
    "raw": "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/README.md",
    "release": "https://github.com/git-for-windows/git/releases/download/v2.50.0.windows.1/Git-2.50.0-64-bit.exe",
}

HEARTBEAT_INTERVAL = 6 * 60 * 60


class AntiJitterPolicy:
    """防抖动策略"""

    SWITCH_THRESHOLD = 0.8
    FAILURE_THRESHOLD = 2

    def __init__(self):
        self.failure_counts: Dict[str, int] = {}

    def should_switch(
        self,
        current_mirror: str,
        current_latency: int,
        new_mirror: str,
        new_latency: int,
    ) -> bool:
        if new_latency < current_latency * self.SWITCH_THRESHOLD:
            return True
        if self.failure_counts.get(current_mirror, 0) >= self.FAILURE_THRESHOLD:
            return True
        return False

    def record_failure(self, mirror: str):
        self.failure_counts[mirror] = self.failure_counts.get(mirror, 0) + 1

    def reset_failure(self, mirror: str):
        self.failure_counts[mirror] = 0

    def reset_all(self):
        self.failure_counts.clear()


class GitHubMirrorManager:
    """GitHub 镜像源管理器"""

    _instance: Optional["GitHubMirrorManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, settings_manager=None):
        if self._initialized:
            return

        self._settings_manager = settings_manager
        self._scheduler = MirrorScheduler(self)
        self._speed_tester = MirrorSpeedTester(self)
        self._anti_jitter = AntiJitterPolicy()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()
        self._speed_test_running = False
        self._speed_test_progress: List[Dict] = []
        self._speed_test_results: Optional[Dict] = None
        self._initialized = True

        logger.info("[GitHubMirrorManager] 初始化完成")

    @property
    def settings_manager(self):
        if self._settings_manager is None:
            from backend.src.core.settings_manager import SettingsManager
            self._settings_manager = SettingsManager()
        return self._settings_manager

    def _load_settings(self) -> Dict:
        try:
            config = self.settings_manager.load_config()
            return config.get("githubMirror", {})
        except Exception:
            return {}

    def _save_settings(self, mirror_settings: Dict):
        try:
            self.settings_manager.update_settings({"githubMirror": mirror_settings})
        except Exception as e:
            logger.error(f"[GitHubMirrorManager] 保存镜像设置失败: {e}")

    def is_enabled(self) -> bool:
        return self._load_settings().get("enabled", False)

    def get_mode(self) -> str:
        return self._load_settings().get("mode", "auto")

    def get_force_preset(self) -> Optional[str]:
        return self._load_settings().get("forcePreset", None)

    def get_current_preset_name(self) -> str:
        if not self.is_enabled():
            return ""
        mode = self.get_mode()
        if mode == "manual" and self.get_force_preset():
            preset = self.get_force_preset()
            if preset in MIRROR_PRESETS:
                return preset
        return self._scheduler.current_preset or "hybrid"

    def get_current_preset(self) -> Optional[Dict]:
        name = self.get_current_preset_name()
        if name:
            return MIRROR_PRESETS.get(name)
        return None

    def get_mirror_for_type(self, url_type: str) -> Optional[str]:
        if not self.is_enabled():
            return None
        preset = self.get_current_preset()
        if preset:
            return preset.get(url_type)
        return None

    def transform_url(self, url: str, url_type: str) -> Tuple[str, Dict]:
        """
        转换 URL 为镜像 URL

        Args:
            url: 原始 URL
            url_type: URL 类型 (github, raw, release, api)

        Returns:
            (transformed_url, headers)
        """
        if not self.is_enabled():
            return url, {}

        mirror = self.get_mirror_for_type(url_type)
        if not mirror:
            return url, {}

        headers = self._get_recommended_headers(mirror, url_type)
        transformed = self._do_transform(url, mirror, url_type)
        return transformed, headers

    def _do_transform(self, url: str, mirror: str, url_type: str) -> str:
        if url_type == "github":
            if "github.com" in url:
                return url.replace("https://github.com", f"https://{mirror}/github.com", 1)
            return url

        if url_type == "raw":
            if "raw.githubusercontent.com" in url:
                return f"https://{mirror}/{url}"
            return url

        if url_type == "release":
            if "github.com" in url and "/releases/" in url:
                return f"https://{mirror}/{url}"
            return url

        if url_type == "api":
            return url

        return url

    def _get_recommended_headers(self, mirror: str, url_type: str) -> Dict:
        headers = {}
        if mirror in MIRROR_USER_AGENTS:
            headers["User-Agent"] = MIRROR_USER_AGENTS[mirror]
        if url_type == "raw":
            headers["Referer"] = "https://github.com/"
        return headers

    def get_git_env_with_mirror(
        self, mirror: Optional[str] = None, mingit_path: Optional[Path] = None
    ) -> Dict:
        """
        获取带有镜像配置的 Git 环境变量

        Args:
            mirror: 镜像源域名
            mingit_path: MinGit 安装路径（Windows 特有）
        """
        env = os.environ.copy()

        settings = self._load_settings()

        if mirror:
            env["GIT_CONFIG_COUNT"] = "1"
            env["GIT_CONFIG_KEY_0"] = f"url.https://{mirror}/.insteadOf"
            env["GIT_CONFIG_VALUE_0"] = "https://github.com/"

        if not settings.get("verifySSL", True):
            env["GIT_SSL_NO_VERIFY"] = "true"

        if mingit_path and os.name == "nt":
            mingit_bin = str(mingit_path / "cmd")
            current_path = env.get("PATH", "")
            if mingit_bin not in current_path:
                env["PATH"] = f"{mingit_bin}{os.pathsep}{current_path}"

        return env

    def get_status_text(self) -> str:
        if not self.is_enabled():
            return ""
        if self._speed_test_running:
            return "正在测速中..."
        preset_name = self.get_current_preset_name()
        if preset_name:
            latency = self._get_best_latency(preset_name)
            if latency and latency > 0:
                return f"当前节点: {MIRROR_PRESETS[preset_name]['name']} (延迟 {latency}ms)"
            return f"当前节点: {MIRROR_PRESETS[preset_name]['name']}"
        return "镜像加速已启用"

    def _get_best_latency(self, preset_name: str) -> Optional[int]:
        if self._speed_test_results and preset_name in self._speed_test_results:
            results = self._speed_test_results[preset_name]
            valid = [v for v in results.values() if v > 0]
            if valid:
                return min(valid)
        return None

    def enable_mirror(self):
        settings = self._load_settings()
        settings["enabled"] = True
        if "mode" not in settings:
            settings["mode"] = "auto"
        settings["verifySSL"] = False
        self._save_settings(settings)

        if not self._speed_test_results:
            self._scheduler.current_preset = "hybrid"
            self._start_background_speed_test()
        else:
            best = self._scheduler.get_best_mirror(self._speed_test_results)
            self._scheduler.current_preset = best

        self._start_heartbeat()

    def disable_mirror(self):
        settings = self._load_settings()
        settings["enabled"] = False
        settings["verifySSL"] = True
        self._save_settings(settings)
        self._scheduler.current_preset = None
        self._stop_heartbeat()

    def update_settings(self, updates: Dict):
        settings = self._load_settings()
        settings.update(updates)
        self._save_settings(settings)

        if updates.get("enabled") is True:
            self.enable_mirror()
        elif updates.get("enabled") is False:
            self.disable_mirror()

    def get_settings(self) -> Dict:
        settings = self._load_settings()
        settings["statusText"] = self.get_status_text()
        settings["currentPreset"] = self.get_current_preset_name()
        settings["isTesting"] = self._speed_test_running
        settings["testResults"] = self._speed_test_results
        return settings

    def start_speed_test(self) -> Dict:
        if self._speed_test_running:
            return {"success": False, "message": "测速正在进行中"}
        self._speed_test_running = True
        self._speed_test_progress = []
        self._speed_test_results = None
        thread = threading.Thread(target=self._run_speed_test, daemon=True)
        thread.start()
        return {"success": True, "message": "测速已开始"}

    def _run_speed_test(self):
        try:
            results = self._speed_tester.test_all_mirrors(
                progress_callback=self._on_speed_test_progress
            )
            self._speed_test_results = results
            settings = self._load_settings()
            settings["lastTested"] = datetime.now().isoformat()
            settings["testResults"] = results
            self._save_settings(settings)

            if self.is_enabled() and self.get_mode() == "auto":
                best = self._scheduler.get_best_mirror(results)
                current = self._scheduler.current_preset
                if best != current:
                    current_latency = self._get_best_latency(current or "hybrid") or 9999
                    best_latency = self._get_best_latency(best) or 9999
                    if self._anti_jitter.should_switch(
                        current or "hybrid", current_latency, best, best_latency
                    ):
                        self._scheduler.current_preset = best
                        logger.info(f"[GitHubMirrorManager] 自动切换到最优镜像: {best}")
        except Exception as e:
            logger.error(f"[GitHubMirrorManager] 测速失败: {e}")
        finally:
            self._speed_test_running = False

    def _on_speed_test_progress(self, preset_name: str, url_type: str, latency: int):
        self._speed_test_progress.append(
            {
                "preset": preset_name,
                "type": url_type,
                "latency": latency,
                "timestamp": time.time(),
            }
        )

    def get_speed_test_status(self) -> Dict:
        return {
            "isRunning": self._speed_test_running,
            "progress": self._speed_test_progress,
            "results": self._speed_test_results,
        }

    def _start_background_speed_test(self):
        if not self._speed_test_running:
            thread = threading.Thread(target=self._run_speed_test, daemon=True)
            thread.start()

    def _start_heartbeat(self):
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        self._heartbeat_stop.set()

    def _heartbeat_loop(self):
        while not self._heartbeat_stop.wait(timeout=HEARTBEAT_INTERVAL):
            if not self.is_enabled():
                break
            try:
                self._start_background_speed_test()
            except Exception as e:
                logger.error(f"[GitHubMirrorManager] 心跳检测失败: {e}")

    def fetch_with_fallback(
        self,
        url: str,
        url_type: str,
        timeout: int = 30,
        operation_name: str = "下载",
    ) -> Tuple[bytes, Optional[str]]:
        """
        带静默故障转移的请求

        Returns:
            (content, used_mirror)
        """
        if not self.is_enabled():
            return self._fetch_direct(url, timeout), None

        mirrors_to_try = self._get_mirror_priority_list(url_type)

        last_error = None
        for attempt, mirror in enumerate(mirrors_to_try):
            if not mirror:
                continue
            try:
                transformed_url, headers = self.transform_url(url, url_type)
                content = self._fetch_url(transformed_url, headers, mirror, timeout)

                if attempt > 0:
                    self._anti_jitter.reset_failure(mirror)

                return content, mirror

            except Exception as e:
                last_error = e
                self._anti_jitter.record_failure(mirror)
                logger.warning(
                    f"[GitHubMirrorManager] {operation_name}失败 (镜像: {mirror}): {e}"
                )
                continue

        settings = self._load_settings()
        if settings.get("fallbackToDirect", True):
            try:
                return self._fetch_direct(url, timeout), None
            except Exception as e:
                last_error = e

        raise MirrorError(f"所有镜像源均失败: {last_error}")

    def _get_mirror_priority_list(self, url_type: str) -> List[str]:
        preset = self.get_current_preset()
        if not preset:
            return []

        primary = preset.get(url_type)
        fallbacks = preset.get("fallback", {}).get(url_type, [])

        result = []
        if primary:
            result.append(primary)
        result.extend(fallbacks)
        return list(dict.fromkeys(result))

    def _fetch_url(
        self, url: str, headers: Dict, mirror: str, timeout: int
    ) -> bytes:
        all_headers = {"User-Agent": "Comfyui-Box/1.0"}
        all_headers.update(headers)
        response = requests.get(url, headers=all_headers, timeout=timeout)
        response.raise_for_status()
        return response.content

    def _fetch_direct(self, url: str, timeout: int) -> bytes:
        response = requests.get(
            url,
            headers={"User-Agent": "Comfyui-Box/1.0"},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.content


class MirrorScheduler:
    """镜像调度器"""

    def __init__(self, manager: GitHubMirrorManager):
        self.manager = manager
        self.current_preset: Optional[str] = None

    def get_best_mirror(self, speed_results: Dict) -> str:
        if not speed_results:
            return "hybrid"

        scores: Dict[str, float] = {}
        for preset_name, results in speed_results.items():
            valid_latencies = [v for v in results.values() if v > 0]
            if valid_latencies:
                scores[preset_name] = sum(valid_latencies) / len(valid_latencies)

        if scores:
            return min(scores, key=scores.get)

        return "hybrid"


class MirrorSpeedTester:
    """镜像测速器"""

    def __init__(self, manager: GitHubMirrorManager):
        self.manager = manager

    def test_all_mirrors(
        self, progress_callback: Optional[Callable] = None
    ) -> Dict:
        results = {}

        for preset_name, preset in MIRROR_PRESETS.items():
            results[preset_name] = {}

            for url_type in ["github", "raw", "release"]:
                mirror = preset.get(url_type)
                if mirror:
                    if url_type == "github":
                        latency = self._test_git_mirror_speed(mirror)
                    else:
                        latency = self._test_mirror_speed(mirror, url_type)
                    results[preset_name][url_type] = latency
                    if progress_callback:
                        progress_callback(preset_name, url_type, latency)
                else:
                    results[preset_name][url_type] = -1

        return results

    def _test_git_mirror_speed(self, mirror: str) -> int:
        test_repo = "https://github.com/git/git"
        mirror_url = test_repo.replace("https://github.com", f"https://{mirror}/github.com", 1)

        try:
            start_time = time.time()
            result = subprocess.run(
                ["git", "ls-remote", "--exit-code", mirror_url, "HEAD"],
                capture_output=True,
                timeout=30,
                text=True,
            )
            elapsed = int((time.time() - start_time) * 1000)

            if result.returncode == 0:
                return elapsed
            else:
                logger.debug(f"[MirrorSpeedTester] git ls-remote 失败 ({mirror}): {result.stderr}")
                return -1

        except subprocess.TimeoutExpired:
            logger.debug(f"[MirrorSpeedTester] git ls-remote 超时 ({mirror})")
            return -1
        except FileNotFoundError:
            logger.debug("[MirrorSpeedTester] git 命令未找到")
            return -1
        except Exception as e:
            logger.debug(f"[MirrorSpeedTester] git ls-remote 异常 ({mirror}): {e}")
            return -1

    def _test_mirror_speed(self, mirror: str, url_type: str) -> int:
        test_url = SPEED_TEST_FILES.get(url_type)
        if not test_url:
            return -1

        try:
            transformed_url, headers = self._transform_test_url(
                test_url, mirror, url_type
            )
            all_headers = {"User-Agent": "Comfyui-Box/1.0"}
            all_headers.update(headers)

            start_time = time.time()
            response = requests.get(
                transformed_url,
                headers=all_headers,
                timeout=15,
                stream=True,
            )
            response.raise_for_status()

            chunk_size = 4096
            downloaded = 0
            max_download = 64 * 1024
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded >= max_download:
                        break

            elapsed = int((time.time() - start_time) * 1000)
            return elapsed

        except Exception as e:
            logger.debug(f"[MirrorSpeedTester] 测速失败 ({mirror}, {url_type}): {e}")
            return -1

    def _transform_test_url(
        self, url: str, mirror: str, url_type: str
    ) -> Tuple[str, Dict]:
        headers = {}
        if mirror in MIRROR_USER_AGENTS:
            headers["User-Agent"] = MIRROR_USER_AGENTS[mirror]
        if url_type == "raw":
            headers["Referer"] = "https://github.com/"

        transformed = self.manager._do_transform(url, mirror, url_type)
        return transformed, headers


class MirrorError(Exception):
    """镜像源错误"""

    pass


github_mirror_manager = GitHubMirrorManager()
