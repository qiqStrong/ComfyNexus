"""
PyPI 镜像源管理模块

提供 PyPI 国内镜像加速功能，包括：
- 自动调度选择最优镜像
- 测速功能
- 心跳检测
- 防抖动策略
"""

import time
import threading
from typing import Dict, Optional, Callable, List
from datetime import datetime

import requests

from backend.src.utils.logger import app_logger as logger


PYPI_MIRROR_SOURCES = {
    "tuna": {
        "name": "清华大学 (TUNA)",
        "description": "带宽大，同步频率极高，2026年依然是最稳的",
        "pip_index": "https://pypi.tuna.tsinghua.edu.cn/simple",
        "pypi": "https://pypi.tuna.tsinghua.edu.cn",
        "pytorch_index": "https://mirrors.tuna.tsinghua.edu.cn/pytorch/whl",
    },
    "bfsu": {
        "name": "北京外国语 (BFSU)",
        "description": "TUNA 的高可用镜像，负载均衡压力小",
        "pip_index": "https://mirrors.bfsu.edu.cn/pypi/web/simple",
        "pypi": "https://mirrors.bfsu.edu.cn",
        "pytorch_index": None,
    },
    "aliyun": {
        "name": "阿里云",
        "description": "企业级服务，全国 CDN 覆盖，速度极快",
        "pip_index": "https://mirrors.aliyun.com/pypi/simple",
        "pypi": "https://mirrors.aliyun.com",
        "pytorch_index": None,
    },
    "tencent": {
        "name": "腾讯云",
        "description": "公网表现稳定，腾讯云内网访问极快",
        "pip_index": "https://mirrors.cloud.tencent.com/pypi/simple",
        "pypi": "https://mirrors.cloud.tencent.com",
        "pytorch_index": None,
    },
    "official": {
        "name": "官方源",
        "description": "PyPI 官方源，国内访问较慢",
        "pip_index": "https://pypi.org/simple",
        "pypi": "https://pypi.org",
        "pytorch_index": "https://download.pytorch.org/whl",
    },
}

HEARTBEAT_INTERVAL = 6 * 60 * 60


class AntiJitterPolicy:

    SWITCH_THRESHOLD = 0.8
    FAILURE_THRESHOLD = 2

    def __init__(self):
        self.failure_counts: Dict[str, int] = {}

    def should_switch(
        self,
        current_source: str,
        current_latency: int,
        new_source: str,
        new_latency: int,
    ) -> bool:
        if new_latency < current_latency * self.SWITCH_THRESHOLD:
            return True
        if self.failure_counts.get(current_source, 0) >= self.FAILURE_THRESHOLD:
            return True
        return False

    def record_failure(self, source: str):
        self.failure_counts[source] = self.failure_counts.get(source, 0) + 1

    def reset_failure(self, source: str):
        self.failure_counts[source] = 0

    def reset_all(self):
        self.failure_counts.clear()


class PyPIMirrorManager:

    _instance: Optional["PyPIMirrorManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, settings_manager=None):
        if self._initialized:
            return

        self._settings_manager = settings_manager
        self._scheduler = PyPIMirrorScheduler(self)
        self._speed_tester = PyPIMirrorSpeedTester(self)
        self._anti_jitter = AntiJitterPolicy()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()
        self._speed_test_running = False
        self._speed_test_progress: List[Dict] = []
        self._speed_test_results: Optional[Dict] = None
        self._initialized = True

        logger.info("[PyPIMirrorManager] 初始化完成")

    @property
    def settings_manager(self):
        if self._settings_manager is None:
            from backend.src.core.settings_manager import SettingsManager
            self._settings_manager = SettingsManager()
        return self._settings_manager

    def _load_settings(self) -> Dict:
        try:
            config = self.settings_manager.load_config()
            return config.get("pypiMirror", {})
        except Exception:
            return {}


    def _save_settings(self, mirror_settings: Dict):
        try:
            self.settings_manager.update_settings({"pypiMirror": mirror_settings})
        except Exception as e:
            logger.error(f"[PyPIMirrorManager] 保存镜像设置失败: {e}")

    def is_enabled(self) -> bool:
        return self._load_settings().get("enabled", False)

    def get_mode(self) -> str:
        return self._load_settings().get("mode", "auto")

    def get_force_source(self) -> Optional[str]:
        return self._load_settings().get("forceSource", None)

    def get_current_source_name(self) -> str:
        if not self.is_enabled():
            return ""
        mode = self.get_mode()
        if mode == "manual" and self.get_force_source():
            source = self.get_force_source()
            if source in PYPI_MIRROR_SOURCES:
                return source
        return self._scheduler.current_source or "tuna"

    def get_current_source(self) -> Optional[Dict]:
        name = self.get_current_source_name()
        if name:
            return PYPI_MIRROR_SOURCES.get(name)
        return None

    def get_pip_index_url(self) -> str:
        source = self.get_current_source()
        if source:
            return source["pip_index"]
        return PYPI_MIRROR_SOURCES["official"]["pip_index"]

    def get_pypi_api_url(self) -> str:
        source = self.get_current_source()
        if source:
            return source["pypi"]
        return PYPI_MIRROR_SOURCES["official"]["pypi"]

    def get_pytorch_index_url(self, cuda_version: str = "") -> Optional[str]:
        source = self.get_current_source()
        if not source:
            return None
        pytorch_index = source.get("pytorch_index")
        if not pytorch_index:
            return None
        if cuda_version and cuda_version != "cpu":
            cuda_ver = cuda_version.replace(".", "")
            return f"{pytorch_index}/cu{cuda_ver}"
        elif cuda_version == "cpu":
            return f"{pytorch_index}/cpu"
        return pytorch_index

    def get_status_text(self) -> str:
        if not self.is_enabled():
            return ""
        if self._speed_test_running:
            return "正在测速中..."
        source_name = self.get_current_source_name()
        if source_name:
            latency = self._get_source_latency(source_name)
            if latency and latency > 0:
                return f"当前源: {PYPI_MIRROR_SOURCES[source_name]['name']} (延迟 {latency}ms)"
            return f"当前源: {PYPI_MIRROR_SOURCES[source_name]['name']}"
        return "PyPI 镜像加速已启用"

    def _get_source_latency(self, source_name: str) -> Optional[int]:
        if self._speed_test_results and source_name in self._speed_test_results:
            latency = self._speed_test_results[source_name]
            if latency > 0:
                return latency
        return None

    def enable_mirror(self):
        settings = self._load_settings()
        settings["enabled"] = True
        if "mode" not in settings:
            settings["mode"] = "auto"
        self._save_settings(settings)

        if not self._speed_test_results:
            self._scheduler.current_source = "tuna"
            self._start_background_speed_test()
        else:
            best = self._scheduler.get_best_source(self._speed_test_results)
            self._scheduler.current_source = best

        self._start_heartbeat()

    def disable_mirror(self):
        settings = self._load_settings()
        settings["enabled"] = False
        self._save_settings(settings)
        self._scheduler.current_source = None
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
        settings["currentSource"] = self.get_current_source_name()
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
                best = self._scheduler.get_best_source(results)
                current = self._scheduler.current_source
                if best != current:
                    current_latency = self._get_source_latency(current or "tuna") or 9999
                    best_latency = self._get_source_latency(best) or 9999
                    if self._anti_jitter.should_switch(
                        current or "tuna", current_latency, best, best_latency
                    ):
                        self._scheduler.current_source = best
                        logger.info(f"[PyPIMirrorManager] 自动切换到最优镜像: {best}")
        except Exception as e:
            logger.error(f"[PyPIMirrorManager] 测速失败: {e}")
        finally:
            self._speed_test_running = False

    def _on_speed_test_progress(self, source_name: str, latency: int):
        self._speed_test_progress.append(
            {
                "source": source_name,
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
                logger.error(f"[PyPIMirrorManager] 心跳检测失败: {e}")


class PyPIMirrorScheduler:

    def __init__(self, manager: PyPIMirrorManager):
        self.manager = manager
        self.current_source: Optional[str] = None

    def get_best_source(self, speed_results: Dict) -> str:
        if not speed_results:
            return "tuna"

        valid_sources = {}
        for source_name, latency in speed_results.items():
            if latency > 0:
                valid_sources[source_name] = latency

        if valid_sources:
            return min(valid_sources, key=valid_sources.get)

        return "tuna"


class PyPIMirrorSpeedTester:

    def __init__(self, manager: PyPIMirrorManager):
        self.manager = manager

    def test_all_mirrors(
        self, progress_callback: Optional[Callable] = None
    ) -> Dict:
        results = {}

        for source_name, source_info in PYPI_MIRROR_SOURCES.items():
            latency = self._test_mirror_speed(source_info["pip_index"])
            results[source_name] = latency
            if progress_callback:
                progress_callback(source_name, latency)

        return results

    def _test_mirror_speed(self, pip_index_url: str) -> int:
        test_url = pip_index_url.rstrip("/") + "/"
        try:
            start_time = time.time()
            response = requests.get(
                test_url,
                headers={"User-Agent": "Comfyui-Box/1.0"},
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
            logger.debug(f"[PyPIMirrorSpeedTester] 测速失败 ({test_url}): {e}")
            return -1


pypi_mirror_manager = PyPIMirrorManager()
