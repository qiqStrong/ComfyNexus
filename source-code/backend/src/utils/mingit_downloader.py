"""
MinGit 下载器模块

提供 MinGit 的下载、解压和验证功能，支持断点续传。
"""

import os
import sys
import json
import zipfile
import shutil
import requests
from pathlib import Path
from typing import Optional, Callable, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

if TYPE_CHECKING:
    from _hashlib import Hash as HashType
else:
    HashType = object


class DownloadStatus(Enum):
    PENDING = "pending"
    CHECKING_CACHE = "checking_cache"
    DOWNLOADING = "downloading"
    RESUMING = "resuming"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadProgress:
    status: DownloadStatus
    current: int
    total: int
    message: str
    error: Optional[str] = None
    resumed: bool = False
    from_cache: bool = False


@dataclass
class PartialDownloadInfo:
    has_partial: bool = False
    partial_file: str = ""
    downloaded_size: int = 0
    total_size: int = 0
    percentage: int = 0
    version_match: bool = False


DEFAULT_VERSION = "2.53.0.2"
DEFAULT_DOWNLOAD_URL = "https://github.com/git-for-windows/git/releases/download/v{version}/MinGit-{version}-64-bit.zip"

LATEST_RELEASE_CACHE = None
LATEST_RELEASE_CACHE_TIME = 0
CACHE_DURATION = 3600

CHUNK_SIZE = 8192
REQUEST_TIMEOUT = 60


@dataclass
class MinGitReleaseInfo:
    """MinGit 发布信息"""
    tag: str
    version: str
    download_url: str
    fallback_url: str


def get_latest_mingit_release() -> MinGitReleaseInfo:
    """
    从 GitHub API 获取最新的 MinGit 发布信息，包括下载链接
    
    从 GitHub API 获取最新的稳定版本号和下载链接，并缓存 1 小时。
    如果启用了镜像加速，使用镜像 URL 获取。
    
    Returns:
        MinGitReleaseInfo: 包含 tag、版本号和下载链接的信息
    """
    global LATEST_RELEASE_CACHE, LATEST_RELEASE_CACHE_TIME
    
    import time
    import re
    current_time = time.time()
    
    if LATEST_RELEASE_CACHE and (current_time - LATEST_RELEASE_CACHE_TIME) < CACHE_DURATION:
        return LATEST_RELEASE_CACHE
    
    try:
        url = "https://api.github.com/repos/git-for-windows/git/releases/latest"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Comfyui-Box",
            "Accept": "application/vnd.github.v3+json"
        }
        
        verify_ssl = True
        try:
            from backend.src.utils.github_mirror import github_mirror_manager
            if github_mirror_manager.is_enabled():
                mirror_url, mirror_headers = github_mirror_manager.transform_url(url, "api")
                url = mirror_url
                headers.update(mirror_headers)
                settings = github_mirror_manager._load_settings()
                verify_ssl = settings.get("verifySSL", True)
        except Exception:
            pass
        
        response = requests.get(url, headers=headers, timeout=10, verify=verify_ssl)
        response.raise_for_status()
        data = response.json()
        
        tag_name = data.get("tag_name", "")
        
        version = tag_name
        if version.startswith("v"):
            version = version[1:]
        
        version = re.sub(r'\.windows\b', '', version, flags=re.IGNORECASE)
        
        download_url = None
        assets = data.get("assets", [])
        for asset in assets:
            asset_name = asset.get("name", "")
            if "MinGit" in asset_name and "64-bit" in asset_name and asset_name.endswith(".zip"):
                download_url = asset.get("browser_download_url", "")
                print(f"[MinGit] 从 GitHub API 获取到下载链接: {asset_name}")
                break
        
        if not download_url:
            print(f"[MinGit] 未在 assets 中找到 MinGit 64-bit.zip，使用备用 URL 模板")
            download_url = DEFAULT_DOWNLOAD_URL.format(version=version)
        
        fallback_url = DEFAULT_DOWNLOAD_URL.format(version=version)
        
        release_info = MinGitReleaseInfo(
            tag=tag_name,
            version=version,
            download_url=download_url,
            fallback_url=fallback_url
        )
        
        LATEST_RELEASE_CACHE = release_info
        LATEST_RELEASE_CACHE_TIME = current_time
        
        return release_info
        
    except Exception as e:
        print(f"获取最新版本号失败：{e}，使用默认版本")
        fallback_url = DEFAULT_DOWNLOAD_URL.format(version=DEFAULT_VERSION)
        return MinGitReleaseInfo(
            tag=f"v{DEFAULT_VERSION}",
            version=DEFAULT_VERSION,
            download_url=fallback_url,
            fallback_url=fallback_url
        )


def get_latest_mingit_version() -> tuple[str, str]:
    """
    自动获取最新的 MinGit 版本号和 tag
    
    从 GitHub API 获取最新的稳定版本号，并缓存 1 小时。
    如果启用了镜像加速，使用镜像 URL 获取。
    
    Returns:
        tuple[str, str]: (tag 名称，解析后的版本号)
    """
    release_info = get_latest_mingit_release()
    return release_info.tag, release_info.version


class MinGitDownloader:
    """
    MinGit 下载器
    
    支持从多个镜像源下载 MinGit，提供进度回调，支持断点续传。
    """
    
    def __init__(self, version: str = None):
        """
        初始化下载器
        
        Args:
            version: MinGit 版本号，如果为 None 则自动获取最新版本
        """
        if version:
            self.tag = f"v{version}"
            self.version = version
            self._release_info = None
        else:
            self._release_info = get_latest_mingit_release()
            self.tag = self._release_info.tag
            self.version = self._release_info.version
        
        self._cancelled = False
        self._current_progress = DownloadProgress(
            status=DownloadStatus.PENDING,
            current=0,
            total=0,
            message="准备下载"
        )
        self._cache_dir: Optional[Path] = None
    
    def _get_cache_dir(self) -> Path:
        """获取缓存目录"""
        if self._cache_dir is None:
            from backend.src.utils.paths import get_cache_dir
            self._cache_dir = get_cache_dir("mingit")
        return self._cache_dir
    
    def _get_cache_file_path(self) -> Path:
        """获取缓存文件路径"""
        return self._get_cache_dir() / f"MinGit-{self.version}-64-bit.zip"
    
    def _get_partial_file_path(self) -> Path:
        """获取部分下载文件路径"""
        return self._get_cache_dir() / f"MinGit-{self.version}-64-bit.zip.downloading"
    
    def _get_metadata_path(self) -> Path:
        """获取元数据文件路径"""
        return self._get_cache_dir() / f"MinGit-{self.version}-64-bit.zip.meta"
    
    def _save_download_metadata(self, metadata: Dict) -> bool:
        """保存下载元数据"""
        try:
            metadata["last_updated_at"] = datetime.now().isoformat()
            meta_path = self._get_metadata_path()
            
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"保存元数据失败: {e}")
            return False
    
    def _load_download_metadata(self) -> Optional[Dict]:
        """加载下载元数据"""
        try:
            meta_path = self._get_metadata_path()
            
            if not meta_path.exists():
                return None
            
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"加载元数据失败: {e}")
            return None
    
    def _cleanup_partial_download(self) -> bool:
        """清理部分下载文件和元数据"""
        try:
            partial_file = self._get_partial_file_path()
            meta_file = self._get_metadata_path()
            
            if partial_file.exists():
                partial_file.unlink()
            
            if meta_file.exists():
                meta_file.unlink()
            
            return True
        except Exception as e:
            print(f"清理部分下载失败: {e}")
            return False
    
    def check_local_cache(self) -> Dict:
        """
        检查本地是否已有下载完成的 MinGit 缓存
        
        Returns:
            {
                "exists": bool,
                "file_path": str,
                "file_size": int,
                "valid": bool
            }
        """
        cache_file = self._get_cache_file_path()
        
        result = {
            "exists": False,
            "file_path": "",
            "file_size": 0,
            "valid": False
        }
        
        if not cache_file.exists():
            return result
        
        result["exists"] = True
        result["file_path"] = str(cache_file)
        result["file_size"] = cache_file.stat().st_size
        
        valid, _ = self._validate_zip(cache_file)
        result["valid"] = valid
        
        return result
    
    def get_partial_download_info(self) -> PartialDownloadInfo:
        """
        获取部分下载信息
        
        Returns:
            PartialDownloadInfo: 部分下载信息
        """
        result = PartialDownloadInfo()
        
        partial_file = self._get_partial_file_path()
        
        if not partial_file.exists():
            return result
        
        metadata = self._load_download_metadata()
        
        if not metadata:
            return result
        
        result.has_partial = True
        result.partial_file = str(partial_file)
        result.downloaded_size = partial_file.stat().st_size
        result.total_size = metadata.get("total_size", 0)
        result.version_match = metadata.get("version") == self.version
        
        if result.total_size > 0:
            result.percentage = int(result.downloaded_size / result.total_size * 100)
        
        return result
    
    def get_download_urls(self) -> list[str]:
        """
        获取所有可用的下载 URL
        
        Returns:
            list[str]: 下载 URL 列表
        """
        urls = []
        if self._release_info and self._release_info.download_url:
            urls.append(self._release_info.download_url)
        if self._release_info and self._release_info.fallback_url:
            if self._release_info.fallback_url not in urls:
                urls.append(self._release_info.fallback_url)
        if not urls:
            urls.append(DEFAULT_DOWNLOAD_URL.format(version=self.version))
        return urls
    
    def download(
        self,
        target_dir: Path,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> tuple[bool, str]:
        """
        下载并解压 MinGit，支持断点续传
        
        Args:
            target_dir: 目标目录
            progress_callback: 进度回调函数
            
        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        self._cancelled = False
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self._current_progress = DownloadProgress(
                status=DownloadStatus.CHECKING_CACHE,
                current=0,
                total=0,
                message="检查本地缓存..."
            )
            if progress_callback:
                progress_callback(self._current_progress)
            
            cache_info = self.check_local_cache()
            
            if cache_info["exists"] and cache_info["valid"]:
                self._current_progress = DownloadProgress(
                    status=DownloadStatus.DOWNLOADING,
                    current=100,
                    total=100,
                    message="使用本地缓存文件...",
                    from_cache=True
                )
                if progress_callback:
                    progress_callback(self._current_progress)
                
                success, message = self._extract_zip(
                    Path(cache_info["file_path"]), 
                    target_dir, 
                    progress_callback
                )
                
                if success:
                    self._current_progress = DownloadProgress(
                        status=DownloadStatus.COMPLETED,
                        current=100,
                        total=100,
                        message="MinGit 安装完成（使用缓存）",
                        from_cache=True
                    )
                    if progress_callback:
                        progress_callback(self._current_progress)
                    return True, f"MinGit {self.version} 安装成功（使用缓存）"
                
                return False, message
            
            partial_info = self.get_partial_download_info()
            
            zip_path = self._get_cache_file_path()
            partial_path = self._get_partial_file_path()
            
            download_success = False
            last_error = ""
            resumed = False
            
            download_urls = self.get_download_urls()
            
            for idx, url in enumerate(download_urls):
                if self._cancelled:
                    return False, "下载已取消"
                
                verify_ssl = True
                
                try:
                    from backend.src.utils.github_mirror import github_mirror_manager
                    if github_mirror_manager.is_enabled():
                        mirror_url, _ = github_mirror_manager.transform_url(url, "release")
                        url = mirror_url
                        settings = github_mirror_manager._load_settings()
                        verify_ssl = settings.get("verifySSL", True)
                except Exception:
                    pass
                
                if partial_info.has_partial and partial_info.version_match:
                    success, message, was_resumed = self._download_with_resume(
                        url, partial_path, partial_info.downloaded_size, progress_callback, verify_ssl
                    )
                    resumed = was_resumed
                else:
                    if partial_info.has_partial:
                        self._cleanup_partial_download()
                    
                    success, message = self._download_fresh(url, partial_path, progress_callback, verify_ssl)
                
                if success:
                    valid, validate_msg = self._validate_zip(partial_path)
                    if valid:
                        if partial_path != zip_path:
                            if zip_path.exists():
                                zip_path.unlink()
                            partial_path.rename(zip_path)
                        download_success = True
                        break
                    else:
                        success = False
                        message = validate_msg
                        if partial_path.exists():
                            partial_path.unlink()
                        self._cleanup_partial_download()
                
                last_error = f"URL {idx + 1}: {message}"
                
                if partial_path.exists():
                    partial_path.unlink()
                
                self._current_progress = DownloadProgress(
                    status=DownloadStatus.DOWNLOADING,
                    current=0,
                    total=0,
                    message=f"下载源 {idx + 1} 失败，尝试下一个..."
                )
                if progress_callback:
                    progress_callback(self._current_progress)
            
            if not download_success:
                self._current_progress = DownloadProgress(
                    status=DownloadStatus.FAILED,
                    current=0,
                    total=0,
                    message="所有镜像源均下载失败",
                    error=last_error
                )
                if progress_callback:
                    progress_callback(self._current_progress)
                return False, f"所有镜像源均下载失败，请检查网络连接\n{last_error}"
            
            if self._cancelled:
                self._current_progress = DownloadProgress(
                    status=DownloadStatus.CANCELLED,
                    current=0,
                    total=0,
                    message="下载已取消"
                )
                if progress_callback:
                    progress_callback(self._current_progress)
                return False, "下载已取消"
            
            self._current_progress = DownloadProgress(
                status=DownloadStatus.EXTRACTING,
                current=0,
                total=0,
                message="正在解压...",
                resumed=resumed
            )
            if progress_callback:
                progress_callback(self._current_progress)
            
            success, message = self._extract_zip(zip_path, target_dir, progress_callback)
            
            if not success:
                self._current_progress = DownloadProgress(
                    status=DownloadStatus.FAILED,
                    current=0,
                    total=0,
                    message="解压失败",
                    error=message
                )
                if progress_callback:
                    progress_callback(self._current_progress)
                return False, message
            
            git_exe = target_dir / "cmd" / "git.exe"
            if not git_exe.exists():
                git_exe_alt = target_dir / "mingw64" / "bin" / "git.exe"
                if git_exe_alt.exists():
                    target_dir_cmd = target_dir / "cmd"
                    target_dir_cmd.mkdir(exist_ok=True)
                    shutil.copy2(str(git_exe_alt), str(git_exe))
            
            self._cleanup_old_cache()
            
            self._current_progress = DownloadProgress(
                status=DownloadStatus.COMPLETED,
                current=100,
                total=100,
                message="MinGit 安装完成",
                resumed=resumed
            )
            if progress_callback:
                progress_callback(self._current_progress)
            
            return True, f"MinGit {self.version} 安装成功"
            
        except Exception as e:
            self._current_progress = DownloadProgress(
                status=DownloadStatus.FAILED,
                current=0,
                total=0,
                message="安装失败",
                error=str(e)
            )
            if progress_callback:
                progress_callback(self._current_progress)
            return False, f"安装失败: {str(e)}"
    
    def _get_proxies(self) -> Optional[Dict]:
        """获取代理配置
        
        优先级：
        1. 环境变量 HTTP_PROXY / http_proxy
        2. Windows 系统代理设置
        """
        proxy_host = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        
        if not proxy_host:
            try:
                from backend.src.core.system_proxy_manager import SystemProxyManager
                proxy_manager = SystemProxyManager()
                result = proxy_manager.get_system_proxy()
                if result.get("success") and result.get("enabled"):
                    host = result.get("host", "")
                    port = result.get("port", "")
                    if host and port:
                        proxy_host = f"{host}:{port}"
                        print(f"[MinGitDownloader] 使用系统代理: {proxy_host}")
            except Exception as e:
                print(f"[MinGitDownloader] 获取系统代理失败: {e}")
        
        if not proxy_host:
            return None
        
        if "://" in proxy_host:
            proxy_host = proxy_host.split("://")[1]
        
        return {
            "http": f"http://{proxy_host}",
            "https": f"http://{proxy_host}"
        }
    
    def _download_fresh(
        self,
        url: str,
        dest: Path,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        verify_ssl: bool = True
    ) -> tuple[bool, str]:
        """
        全新下载
        
        Args:
            url: 下载 URL
            dest: 目标文件路径
            progress_callback: 进度回调
            verify_ssl: 是否验证 SSL 证书
            
        Returns:
            tuple[bool, str]: (是否成功，消息)
        """
        self._current_progress = DownloadProgress(
            status=DownloadStatus.DOWNLOADING,
            current=0,
            total=0,
            message=f"正在下载 MinGit {self.version}..."
        )
        if progress_callback:
            progress_callback(self._current_progress)
        
        metadata = {
            "url": url,
            "filename": dest.name,
            "version": self.version,
            "downloaded_size": 0,
            "total_size": 0,
            "started_at": datetime.now().isoformat()
        }
        self._save_download_metadata(metadata)
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Comfyui-Box"
            }
            
            try:
                from backend.src.utils.github_mirror import github_mirror_manager
                if github_mirror_manager.is_enabled():
                    _, mirror_headers = github_mirror_manager.transform_url(url, "release")
                    headers.update(mirror_headers)
            except Exception:
                pass
            
            proxies = self._get_proxies()
            
            response = requests.get(
                url, 
                headers=headers, 
                stream=True, 
                timeout=REQUEST_TIMEOUT,
                proxies=proxies,
                verify=verify_ssl
            )
            
            if response.status_code != 200:
                return False, f"HTTP 错误 {response.status_code}"
            
            total_size = int(response.headers.get("content-length", 0))
            metadata["total_size"] = total_size
            
            downloaded = 0
            
            with open(dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if self._cancelled:
                        metadata["downloaded_size"] = downloaded
                        self._save_download_metadata(metadata)
                        return False, "下载已取消"
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        metadata["downloaded_size"] = downloaded
                        if downloaded % (CHUNK_SIZE * 100) == 0:
                            self._save_download_metadata(metadata)
                        
                        self._current_progress = DownloadProgress(
                            status=DownloadStatus.DOWNLOADING,
                            current=downloaded,
                            total=total_size,
                            message=f"下载中... {self._format_size(downloaded)}/{self._format_size(total_size)}"
                        )
                        if progress_callback:
                            progress_callback(self._current_progress)
            
            self._save_download_metadata(metadata)
            return True, "下载完成"
            
        except requests.exceptions.Timeout:
            metadata["downloaded_size"] = downloaded if 'downloaded' in locals() else 0
            self._save_download_metadata(metadata)
            return False, "连接超时"
        except requests.exceptions.ConnectionError:
            metadata["downloaded_size"] = downloaded if 'downloaded' in locals() else 0
            self._save_download_metadata(metadata)
            return False, "网络连接失败"
        except Exception as e:
            return False, f"下载失败: {str(e)}"
    
    def _download_with_resume(
        self,
        url: str,
        dest: Path,
        existing_size: int,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        verify_ssl: bool = True
    ) -> tuple[bool, str, bool]:
        """
        断点续传下载
        
        Args:
            url: 下载 URL
            dest: 目标文件路径
            existing_size: 已下载大小
            progress_callback: 进度回调
            verify_ssl: 是否验证 SSL 证书
            
        Returns:
            tuple[bool, str, bool]: (是否成功，消息，是否真正续传)
        """
        self._current_progress = DownloadProgress(
            status=DownloadStatus.RESUMING,
            current=existing_size,
            total=0,
            message=f"继续下载 MinGit {self.version}...",
            resumed=True
        )
        if progress_callback:
            progress_callback(self._current_progress)
        
        metadata = self._load_download_metadata()
        if not metadata:
            metadata = {
                "url": url,
                "filename": dest.name,
                "version": self.version,
                "downloaded_size": existing_size,
                "total_size": 0,
                "started_at": datetime.now().isoformat()
            }
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Comfyui-Box",
                "Range": f"bytes={existing_size}-"
            }
            
            try:
                from backend.src.utils.github_mirror import github_mirror_manager
                if github_mirror_manager.is_enabled():
                    _, mirror_headers = github_mirror_manager.transform_url(url, "release")
                    headers.update(mirror_headers)
            except Exception:
                pass
            
            proxies = self._get_proxies()
            
            response = requests.get(
                url, 
                headers=headers, 
                stream=True, 
                timeout=REQUEST_TIMEOUT,
                proxies=proxies,
                verify=verify_ssl
            )
            
            if response.status_code == 416:
                if dest.exists() and dest.stat().st_size >= metadata.get("total_size", 0):
                    return True, "下载完成", True
                self._cleanup_partial_download()
                return self._download_fresh(url, dest, progress_callback, verify_ssl) + (False,)
            
            if response.status_code not in (200, 206):
                return False, f"HTTP 错误 {response.status_code}", False
            
            is_resuming = response.status_code == 206
            
            if not is_resuming:
                self._cleanup_partial_download()
                return self._download_fresh(url, dest, progress_callback) + (False,)
            
            total_size = int(response.headers.get("content-length", 0)) + existing_size
            metadata["total_size"] = total_size
            
            downloaded = existing_size
            
            with open(dest, "ab") as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if self._cancelled:
                        metadata["downloaded_size"] = downloaded
                        self._save_download_metadata(metadata)
                        return False, "下载已取消", True
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        metadata["downloaded_size"] = downloaded
                        if downloaded % (CHUNK_SIZE * 100) == 0:
                            self._save_download_metadata(metadata)
                        
                        self._current_progress = DownloadProgress(
                            status=DownloadStatus.RESUMING,
                            current=downloaded,
                            total=total_size,
                            message=f"下载中... {self._format_size(downloaded)}/{self._format_size(total_size)}",
                            resumed=True
                        )
                        if progress_callback:
                            progress_callback(self._current_progress)
            
            self._save_download_metadata(metadata)
            return True, "下载完成", True
            
        except requests.exceptions.Timeout:
            metadata["downloaded_size"] = downloaded if 'downloaded' in locals() else existing_size
            self._save_download_metadata(metadata)
            return False, "连接超时", True
        except requests.exceptions.ConnectionError:
            metadata["downloaded_size"] = downloaded if 'downloaded' in locals() else existing_size
            self._save_download_metadata(metadata)
            return False, "网络连接失败", True
        except Exception as e:
            return False, f"下载失败: {str(e)}", True
    
    def _validate_zip(self, zip_path: Path) -> tuple[bool, str]:
        """
        验证 ZIP 文件是否有效
        
        Args:
            zip_path: ZIP 文件路径
            
        Returns:
            tuple[bool, str]: (是否有效, 消息)
        """
        try:
            if not zip_path.exists():
                return False, "文件不存在"
            
            file_size = zip_path.stat().st_size
            if file_size < 1000:
                return False, f"文件过小 ({file_size} bytes)，可能下载失败"
            
            with open(zip_path, "rb") as f:
                header = f.read(4)
            
            if header[:4] != b'PK\x03\x04' and header[:4] != b'PK\x05\x06':
                with open(zip_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(500)
                    if "<!DOCTYPE" in content or "<html" in content.lower():
                        return False, "下载的是错误页面，请检查网络或使用代理"
                return False, "文件格式无效，不是有效的 ZIP 文件"
            
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    if not zf.namelist():
                        return False, "ZIP 文件为空"
            except zipfile.BadZipFile:
                return False, "ZIP 文件损坏"
            
            return True, "文件有效"
            
        except Exception as e:
            return False, f"验证失败: {str(e)}"
    
    def _extract_zip(
        self,
        zip_path: Path,
        dest_dir: Path,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ) -> tuple[bool, str]:
        """
        解压 ZIP 文件
        
        Args:
            zip_path: ZIP 文件路径
            dest_dir: 目标目录
            progress_callback: 进度回调
            
        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                file_list = zf.namelist()
                total_files = len(file_list)
                extracted = 0
                
                root_folder = None
                if file_list:
                    first_part = file_list[0].split("/")[0]
                    if first_part.startswith("MinGit"):
                        root_folder = first_part
                
                for member in file_list:
                    if self._cancelled:
                        return False, "解压已取消"
                    
                    if root_folder and member.startswith(root_folder + "/"):
                        target_member = member[len(root_folder) + 1:]
                    else:
                        target_member = member
                    
                    if not target_member:
                        continue
                    
                    target_path = dest_dir / target_member
                    
                    if member.endswith("/"):
                        target_path.mkdir(parents=True, exist_ok=True)
                    else:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(target_path, "wb") as dst:
                            dst.write(src.read())
                    
                    extracted += 1
                    
                    if extracted % 50 == 0 or extracted == total_files:
                        self._current_progress = DownloadProgress(
                            status=DownloadStatus.EXTRACTING,
                            current=extracted,
                            total=total_files,
                            message=f"解压中... {extracted}/{total_files} 文件"
                        )
                        if progress_callback:
                            progress_callback(self._current_progress)
            
            return True, "解压完成"
            
        except zipfile.BadZipFile:
            return False, "ZIP 文件损坏"
        except Exception as e:
            return False, f"解压失败: {str(e)}"
    
    def _cleanup_old_cache(self):
        """清理旧版本的缓存文件"""
        try:
            cache_dir = self._get_cache_dir()
            current_prefix = f"MinGit-{self.version}"
            
            for file in cache_dir.iterdir():
                if file.name.startswith("MinGit-") and not file.name.startswith(current_prefix):
                    try:
                        file.unlink()
                        print(f"已清理旧版本缓存: {file.name}")
                    except Exception:
                        pass
        except Exception as e:
            print(f"清理旧缓存失败: {e}")
    
    def cancel(self):
        """取消下载"""
        self._cancelled = True
    
    def get_current_progress(self) -> DownloadProgress:
        """获取当前进度"""
        return self._current_progress
    
    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"


def download_mingit(
    target_dir: Path,
    version: str = None,
    progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
) -> tuple[bool, str]:
    """
    下载 MinGit（便捷函数）
    
    Args:
        target_dir: 目标目录
        version: MinGit 版本，如果为 None 则自动获取最新版本
        progress_callback: 进度回调
        
    Returns:
        tuple[bool, str]: (是否成功，消息)
    """
    downloader = MinGitDownloader(version)
    return downloader.download(target_dir, progress_callback)
