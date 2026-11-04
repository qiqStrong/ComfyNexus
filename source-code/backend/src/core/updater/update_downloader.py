"""
下载管理器
用于下载更新包，支持断点续传和本地文件检查
"""

import os
import json
import hashlib
import requests
from typing import Dict, Optional, Callable, TYPE_CHECKING
from pathlib import Path
from datetime import datetime

from backend.src.utils.logger import app_logger as logger

if TYPE_CHECKING:
    from _hashlib import Hash as HashType
else:
    HashType = object


class UpdateDownloader:
    """更新包下载管理器，支持断点续传"""
    
    CHUNK_SIZE = 8192
    REQUEST_TIMEOUT = 30
    
    def __init__(self, temp_dir: Optional[str] = None, settings_manager=None):
        """
        初始化下载管理器
        
        Args:
            temp_dir: 临时目录路径，为 None 时使用更新缓存目录
            settings_manager: 设置管理器实例（用于获取代理配置）
        """
        self._temp_dir = temp_dir or self._get_default_temp_dir()
        self._settings_manager = settings_manager
        self._downloaded_path: Optional[str] = None
        self._is_downloading = False
        self._cancel_flag = False
        self._current_metadata: Optional[Dict] = None
    
    def _get_proxy_config(self) -> Optional[Dict]:
        """
        获取代理配置
        
        Returns:
            dict: 代理配置 {"http": "...", "https": "..."}
            None: 如果代理未启用或配置无效
        """
        try:
            if not self._settings_manager:
                from backend.src.core.settings_manager import SettingsManager
                self._settings_manager = SettingsManager()
            
            result = self._settings_manager.get_settings()
            
            if not result.get("success"):
                return None
            
            settings = result.get("settings", {})
            proxy = settings.get("proxy", {})
            
            if not proxy.get("enabled"):
                return None
            
            host = proxy.get("host", "").strip()
            port = proxy.get("port", "").strip()
            
            if not host or not port:
                return None
            
            proxy_url = f"http://{host}:{port}"
            
            logger.debug(f"[UpdateDownloader] 使用代理: {proxy_url}")
            
            return {
                "http": proxy_url,
                "https": proxy_url
            }
        except Exception as e:
            logger.error(f"[UpdateDownloader] 获取代理配置失败: {e}")
            return None
    
    def _get_default_temp_dir(self) -> str:
        from backend.src.utils.paths import get_update_cache_dir
        return str(get_update_cache_dir())
    
    def calculate_file_hash(self, file_path: str) -> str:
        """
        计算文件的 SHA256 hash
        
        Args:
            file_path: 文件路径
            
        Returns:
            SHA256 hash 字符串
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(self.CHUNK_SIZE), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def check_local_file(self, expected_hash: str, filename: str) -> Dict:
        """
        检查本地是否已有匹配的更新包
        
        Args:
            expected_hash: 预期的 SHA256 hash
            filename: 文件名
            
        Returns:
            {
                "exists": bool,
                "file_path": str,
                "hash_match": bool,
                "file_size": int
            }
        """
        file_path = os.path.join(self._temp_dir, filename)
        
        result = {
            "exists": False,
            "file_path": "",
            "hash_match": False,
            "file_size": 0
        }
        
        if not os.path.exists(file_path):
            logger.debug(f"[UpdateDownloader] 本地文件不存在: {file_path}")
            return result
        
        result["exists"] = True
        result["file_path"] = file_path
        result["file_size"] = os.path.getsize(file_path)
        
        if expected_hash:
            logger.info(f"[UpdateDownloader] 正在验证本地文件 hash: {file_path}")
            actual_hash = self.calculate_file_hash(file_path)
            result["hash_match"] = actual_hash.lower() == expected_hash.lower()
            
            if result["hash_match"]:
                logger.info(f"[UpdateDownloader] 本地文件 hash 匹配: {actual_hash[:16]}...")
            else:
                logger.warning(f"[UpdateDownloader] 本地文件 hash 不匹配: {actual_hash[:16]}... != {expected_hash[:16]}...")
        else:
            result["hash_match"] = True
            logger.info(f"[UpdateDownloader] 无预期 hash，跳过验证")
        
        return result
    
    def _get_metadata_path(self, filename: str) -> str:
        """获取元数据文件路径"""
        return os.path.join(self._temp_dir, f"{filename}.meta")
    
    def _get_partial_file_path(self, filename: str) -> str:
        """获取部分下载文件路径"""
        return os.path.join(self._temp_dir, f"{filename}.downloading")
    
    def _save_download_metadata(self, metadata: Dict) -> bool:
        """
        保存下载元数据
        
        Args:
            metadata: 元数据字典
            
        Returns:
            是否保存成功
        """
        try:
            meta_path = self._get_metadata_path(metadata["filename"])
            metadata["last_updated_at"] = datetime.now().isoformat()
            
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            self._current_metadata = metadata
            logger.debug(f"[UpdateDownloader] 已保存元数据: {meta_path}")
            return True
        except Exception as e:
            logger.error(f"[UpdateDownloader] 保存元数据失败: {e}")
            return False
    
    def _load_download_metadata(self, filename: str) -> Optional[Dict]:
        """
        加载下载元数据
        
        Args:
            filename: 文件名
            
        Returns:
            元数据字典，失败返回 None
        """
        try:
            meta_path = self._get_metadata_path(filename)
            
            if not os.path.exists(meta_path):
                return None
            
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            
            logger.debug(f"[UpdateDownloader] 已加载元数据: {meta_path}")
            return metadata
        except Exception as e:
            logger.error(f"[UpdateDownloader] 加载元数据失败: {e}")
            return None
    
    def _cleanup_partial_download(self, filename: str) -> bool:
        """
        清理部分下载文件和元数据
        
        Args:
            filename: 文件名
            
        Returns:
            是否清理成功
        """
        try:
            partial_file = self._get_partial_file_path(filename)
            meta_file = self._get_metadata_path(filename)
            
            if os.path.exists(partial_file):
                os.remove(partial_file)
                logger.info(f"[UpdateDownloader] 已清理部分下载文件: {partial_file}")
            
            if os.path.exists(meta_file):
                os.remove(meta_file)
                logger.info(f"[UpdateDownloader] 已清理元数据文件: {meta_file}")
            
            return True
        except Exception as e:
            logger.error(f"[UpdateDownloader] 清理部分下载失败: {e}")
            return False
    
    def get_partial_download_info(self, filename: str, expected_version: str, expected_hash: str) -> Dict:
        """
        获取部分下载信息（用于断点续传）
        
        Args:
            filename: 文件名
            expected_version: 预期版本号
            expected_hash: 预期 hash
            
        Returns:
            {
                "has_partial": bool,
                "partial_file": str,
                "downloaded_size": int,
                "total_size": int,
                "percentage": int,
                "version_match": bool,
                "hash_match": bool
            }
        """
        result = {
            "has_partial": False,
            "partial_file": "",
            "downloaded_size": 0,
            "total_size": 0,
            "percentage": 0,
            "version_match": False,
            "hash_match": False
        }
        
        partial_file = self._get_partial_file_path(filename)
        
        if not os.path.exists(partial_file):
            return result
        
        metadata = self._load_download_metadata(filename)
        
        if not metadata:
            logger.warning(f"[UpdateDownloader] 发现部分下载文件但无元数据: {partial_file}")
            return result
        
        result["has_partial"] = True
        result["partial_file"] = partial_file
        result["downloaded_size"] = os.path.getsize(partial_file)
        result["total_size"] = metadata.get("expected_size", 0)
        result["version_match"] = metadata.get("version") == expected_version
        result["hash_match"] = metadata.get("expected_hash") == expected_hash
        
        if result["total_size"] > 0:
            result["percentage"] = int(result["downloaded_size"] / result["total_size"] * 100)
        
        logger.info(f"[UpdateDownloader] 发现部分下载: {result['downloaded_size']}/{result['total_size']} ({result['percentage']}%)")
        
        return result
    
    def download(
        self, 
        url: str, 
        file_size: int = 0,
        file_hash: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        dev_token: Optional[str] = None,
        asset_id: Optional[int] = None,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        version: Optional[str] = None
    ) -> Dict:
        """
        下载更新包，支持断点续传
        
        Args:
            url: 下载链接
            file_size: 预期文件大小（字节），用于验证
            file_hash: 预期 SHA256 hash，用于验证文件完整性
            progress_callback: 进度回调函数 (downloaded, total)
            dev_token: 开发模式 Token（优先于 settings.json Token）
            asset_id: GitHub 资产 ID（私有仓库下载需要）
            repo_owner: 仓库所有者（私有仓库下载需要）
            repo_name: 仓库名称（私有仓库下载需要）
            version: 版本号（用于元数据）
            
        Returns:
            {
                "success": bool,
                "zip_path": str,
                "error": str,
                "from_local": bool,
                "resumed": bool
            }
        """
        if self._is_downloading:
            return {
                "success": False,
                "error": "已有下载任务在进行中"
            }
        
        self._is_downloading = True
        self._cancel_flag = False
        
        filename = url.split("/")[-1]
        if not filename.endswith(".zip"):
            filename = f"Comfyui-Box-update-{int(datetime.now().timestamp())}.zip"
        
        try:
            local_check = self.check_local_file(file_hash, filename)
            if local_check["exists"] and local_check["hash_match"]:
                logger.info(f"[UpdateDownloader] 使用本地已存在的文件: {local_check['file_path']}")
                self._downloaded_path = local_check["file_path"]
                return {
                    "success": True,
                    "zip_path": local_check["file_path"],
                    "from_local": True,
                    "resumed": False
                }
            
            partial_info = self.get_partial_download_info(filename, version or "", file_hash or "")
            
            if partial_info["has_partial"] and partial_info["version_match"] and partial_info["hash_match"]:
                logger.info(f"[UpdateDownloader] 发现有效的部分下载，尝试续传")
                return self._download_with_resume(
                    url=url,
                    filename=filename,
                    file_size=file_size,
                    file_hash=file_hash,
                    progress_callback=progress_callback,
                    dev_token=dev_token,
                    asset_id=asset_id,
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    version=version,
                    existing_size=partial_info["downloaded_size"]
                )
            
            if partial_info["has_partial"]:
                logger.info(f"[UpdateDownloader] 部分下载已过期，清理后重新下载")
                self._cleanup_partial_download(filename)
            
            return self._download_fresh(
                url=url,
                filename=filename,
                file_size=file_size,
                file_hash=file_hash,
                progress_callback=progress_callback,
                dev_token=dev_token,
                asset_id=asset_id,
                repo_owner=repo_owner,
                repo_name=repo_name,
                version=version
            )
            
        except Exception as e:
            logger.error(f"[UpdateDownloader] 下载失败: {e}")
            return {
                "success": False,
                "error": f"下载失败: {str(e)}"
            }
        finally:
            self._is_downloading = False
    
    def _download_fresh(
        self,
        url: str,
        filename: str,
        file_size: int,
        file_hash: Optional[str],
        progress_callback: Optional[Callable[[int, int], None]],
        dev_token: Optional[str],
        asset_id: Optional[int],
        repo_owner: Optional[str],
        repo_name: Optional[str],
        version: Optional[str]
    ) -> Dict:
        """全新下载"""
        logger.info(f"[UpdateDownloader] 开始全新下载: {url}")
        
        partial_file = self._get_partial_file_path(filename)
        final_file = os.path.join(self._temp_dir, filename)
        
        metadata = {
            "url": url,
            "filename": filename,
            "expected_hash": file_hash,
            "expected_size": file_size,
            "downloaded_size": 0,
            "started_at": datetime.now().isoformat(),
            "version": version
        }
        self._save_download_metadata(metadata)
        
        download_url, headers = self._prepare_download_request(
            url, dev_token, asset_id, repo_owner, repo_name
        )
        
        proxies = self._get_proxy_config()
        
        try:
            response = requests.get(
                download_url, 
                headers=headers, 
                stream=True, 
                timeout=self.REQUEST_TIMEOUT,
                proxies=proxies
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"下载失败，HTTP 状态码: {response.status_code}"
                }
            
            total_size = int(response.headers.get('content-length', file_size))
            metadata["expected_size"] = total_size
            
            downloaded = 0
            sha256_hash = hashlib.sha256() if file_hash else None
            
            with open(partial_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                    if self._cancel_flag:
                        logger.info("[UpdateDownloader] 下载已取消")
                        metadata["downloaded_size"] = downloaded
                        self._save_download_metadata(metadata)
                        return {
                            "success": False,
                            "error": "下载已取消"
                        }
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if sha256_hash:
                            sha256_hash.update(chunk)
                        
                        metadata["downloaded_size"] = downloaded
                        if downloaded % (self.CHUNK_SIZE * 100) == 0:
                            self._save_download_metadata(metadata)
                        
                        if progress_callback:
                            try:
                                progress_callback(downloaded, total_size)
                            except Exception as e:
                                logger.warning(f"[UpdateDownloader] 进度回调失败: {e}")
            
            return self._finalize_download(
                partial_file=partial_file,
                final_file=final_file,
                downloaded=downloaded,
                total_size=total_size,
                file_hash=file_hash,
                sha256_hash=sha256_hash,
                metadata=metadata,
                resumed=False
            )
            
        except requests.exceptions.Timeout:
            metadata["downloaded_size"] = downloaded if 'downloaded' in locals() else 0
            self._save_download_metadata(metadata)
            logger.error("[UpdateDownloader] 下载超时")
            return {
                "success": False,
                "error": "下载超时，请检查网络连接"
            }
        except requests.exceptions.ConnectionError:
            metadata["downloaded_size"] = downloaded if 'downloaded' in locals() else 0
            self._save_download_metadata(metadata)
            logger.error("[UpdateDownloader] 网络连接失败")
            return {
                "success": False,
                "error": "网络连接失败，请检查网络设置"
            }
    
    def _download_with_resume(
        self,
        url: str,
        filename: str,
        file_size: int,
        file_hash: Optional[str],
        progress_callback: Optional[Callable[[int, int], None]],
        dev_token: Optional[str],
        asset_id: Optional[int],
        repo_owner: Optional[str],
        repo_name: Optional[str],
        version: Optional[str],
        existing_size: int
    ) -> Dict:
        """断点续传下载"""
        logger.info(f"[UpdateDownloader] 开始断点续传，已下载: {existing_size} 字节")
        
        partial_file = self._get_partial_file_path(filename)
        final_file = os.path.join(self._temp_dir, filename)
        
        metadata = self._load_download_metadata(filename)
        if not metadata:
            metadata = {
                "url": url,
                "filename": filename,
                "expected_hash": file_hash,
                "expected_size": file_size,
                "downloaded_size": existing_size,
                "started_at": datetime.now().isoformat(),
                "version": version
            }
        
        download_url, headers = self._prepare_download_request(
            url, dev_token, asset_id, repo_owner, repo_name
        )
        
        headers["Range"] = f"bytes={existing_size}-"
        
        proxies = self._get_proxy_config()
        
        try:
            response = requests.get(
                download_url, 
                headers=headers, 
                stream=True, 
                timeout=self.REQUEST_TIMEOUT,
                proxies=proxies
            )
            
            if response.status_code == 416:
                logger.warning("[UpdateDownloader] Range 请求失败（范围无效），检查文件完整性")
                if os.path.exists(partial_file):
                    actual_size = os.path.getsize(partial_file)
                    if actual_size >= metadata.get("expected_size", 0):
                        return self._finalize_download(
                            partial_file=partial_file,
                            final_file=final_file,
                            downloaded=actual_size,
                            total_size=metadata.get("expected_size", 0),
                            file_hash=file_hash,
                            sha256_hash=None,
                            metadata=metadata,
                            resumed=True
                        )
                self._cleanup_partial_download(filename)
                return self._download_fresh(
                    url, filename, file_size, file_hash, progress_callback,
                    dev_token, asset_id, repo_owner, repo_name, version
                )
            
            if response.status_code not in (200, 206):
                return {
                    "success": False,
                    "error": f"下载失败，HTTP 状态码: {response.status_code}"
                }
            
            is_resuming = response.status_code == 206
            total_size = int(response.headers.get('content-length', 0))
            
            if is_resuming:
                total_size += existing_size
            else:
                logger.warning("[UpdateDownloader] 服务器不支持 Range，重新下载")
                self._cleanup_partial_download(filename)
                return self._download_fresh(
                    url, filename, file_size, file_hash, progress_callback,
                    dev_token, asset_id, repo_owner, repo_name, version
                )
            
            metadata["expected_size"] = total_size
            
            downloaded = existing_size
            sha256_hash = hashlib.sha256() if file_hash else None
            
            if sha256_hash and os.path.exists(partial_file):
                logger.info("[UpdateDownloader] 正在计算已下载部分的 hash...")
                with open(partial_file, "rb") as f:
                    for chunk in iter(lambda: f.read(self.CHUNK_SIZE), b""):
                        sha256_hash.update(chunk)
            
            with open(partial_file, 'ab') as f:
                for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                    if self._cancel_flag:
                        logger.info("[UpdateDownloader] 下载已取消")
                        metadata["downloaded_size"] = downloaded
                        self._save_download_metadata(metadata)
                        return {
                            "success": False,
                            "error": "下载已取消"
                        }
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if sha256_hash:
                            sha256_hash.update(chunk)
                        
                        metadata["downloaded_size"] = downloaded
                        if downloaded % (self.CHUNK_SIZE * 100) == 0:
                            self._save_download_metadata(metadata)
                        
                        if progress_callback:
                            try:
                                progress_callback(downloaded, total_size)
                            except Exception as e:
                                logger.warning(f"[UpdateDownloader] 进度回调失败: {e}")
            
            return self._finalize_download(
                partial_file=partial_file,
                final_file=final_file,
                downloaded=downloaded,
                total_size=total_size,
                file_hash=file_hash,
                sha256_hash=sha256_hash,
                metadata=metadata,
                resumed=True
            )
            
        except requests.exceptions.Timeout:
            metadata["downloaded_size"] = downloaded if 'downloaded' in locals() else existing_size
            self._save_download_metadata(metadata)
            logger.error("[UpdateDownloader] 下载超时")
            return {
                "success": False,
                "error": "下载超时，请检查网络连接"
            }
        except requests.exceptions.ConnectionError:
            metadata["downloaded_size"] = downloaded if 'downloaded' in locals() else existing_size
            self._save_download_metadata(metadata)
            logger.error("[UpdateDownloader] 网络连接失败")
            return {
                "success": False,
                "error": "网络连接失败，请检查网络设置"
            }
    
    def _prepare_download_request(
        self,
        url: str,
        dev_token: Optional[str],
        asset_id: Optional[int],
        repo_owner: Optional[str],
        repo_name: Optional[str]
    ) -> tuple:
        """准备下载请求的 URL 和 headers"""
        download_url = url
        headers = {
            "User-Agent": "Comfyui-Box-UpdateDownloader"
        }
        
        if dev_token and asset_id and repo_owner and repo_name:
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/assets/{asset_id}"
            download_url = api_url
            headers["Authorization"] = f"token {dev_token}"
            headers["Accept"] = "application/octet-stream"
            logger.info(f"[UpdateDownloader] 使用 GitHub API 下载私有仓库资产 (asset_id={asset_id})")
        elif self._settings_manager:
            token = self._settings_manager.get_github_api_token()
            if token and asset_id and repo_owner and repo_name:
                api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/assets/{asset_id}"
                download_url = api_url
                headers["Authorization"] = f"token {token}"
                headers["Accept"] = "application/octet-stream"
                logger.info(f"[UpdateDownloader] 使用 GitHub API 下载私有仓库资产 (asset_id={asset_id})")
        
        if download_url == url:
            try:
                from backend.src.utils.github_mirror import github_mirror_manager
                if github_mirror_manager.is_enabled():
                    mirror = github_mirror_manager.get_mirror_for_type("release")
                    if mirror:
                        transformed_url, extra_headers = github_mirror_manager.transform_url(
                            url, "release"
                        )
                        if transformed_url != url:
                            download_url = transformed_url
                            headers.update(extra_headers)
                            logger.dev(f"[UpdateDownloader] 使用 release 镜像源: {mirror}")
            except Exception as e:
                logger.dev(f"[UpdateDownloader] 获取镜像设置失败: {e}")
        
        return download_url, headers
    
    def _finalize_download(
        self,
        partial_file: str,
        final_file: str,
        downloaded: int,
        total_size: int,
        file_hash: Optional[str],
        sha256_hash: Optional[HashType],
        metadata: Dict,
        resumed: bool
    ) -> Dict:
        """完成下载，验证并移动文件"""
        if total_size > 0 and downloaded != total_size:
            logger.warning(f"[UpdateDownloader] 文件大小不匹配: {downloaded} != {total_size}")
            metadata["downloaded_size"] = downloaded
            self._save_download_metadata(metadata)
            return {
                "success": False,
                "error": "文件大小不匹配，下载可能不完整"
            }
        
        if file_hash and sha256_hash:
            actual_hash = sha256_hash.hexdigest()
            if actual_hash.lower() != file_hash.lower():
                logger.error(f"[UpdateDownloader] SHA256 校验失败: {actual_hash[:16]}... != {file_hash[:16]}...")
                if os.path.exists(partial_file):
                    os.remove(partial_file)
                self._cleanup_partial_download(metadata["filename"])
                return {
                    "success": False,
                    "error": "文件校验失败，文件可能已损坏或被篡改"
                }
            logger.info(f"[UpdateDownloader] SHA256 校验通过: {actual_hash[:16]}...")
        
        if os.path.exists(final_file):
            os.remove(final_file)
        
        os.rename(partial_file, final_file)
        
        meta_path = self._get_metadata_path(metadata["filename"])
        if os.path.exists(meta_path):
            os.remove(meta_path)
        
        self._downloaded_path = final_file
        logger.info(f"[UpdateDownloader] 下载完成: {final_file}")
        
        return {
            "success": True,
            "zip_path": final_file,
            "from_local": False,
            "resumed": resumed
        }
    
    def cancel_download(self):
        """取消当前下载"""
        self._cancel_flag = True
    
    def verify_download(self, file_path: str, expected_size: int) -> bool:
        """
        验证下载文件
        
        Args:
            file_path: 文件路径
            expected_size: 预期文件大小（字节）
            
        Returns:
            验证是否通过
        """
        try:
            if not os.path.exists(file_path):
                logger.warning(f"[UpdateDownloader] 文件不存在: {file_path}")
                return False
            
            actual_size = os.path.getsize(file_path)
            
            if expected_size > 0 and actual_size != expected_size:
                logger.warning(f"[UpdateDownloader] 文件大小不匹配: {actual_size} != {expected_size}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"[UpdateDownloader] 验证文件失败: {e}")
            return False
    
    def cleanup(self):
        """清理临时文件"""
        try:
            if self._downloaded_path and os.path.exists(self._downloaded_path):
                os.remove(self._downloaded_path)
                logger.info(f"[UpdateDownloader] 已清理临时文件: {self._downloaded_path}")
                self._downloaded_path = None
        except Exception as e:
            logger.warning(f"[UpdateDownloader] 清理临时文件失败: {e}")
    
    def cleanup_old_cache(self, current_version: str):
        """
        清理旧版本的缓存文件
        
        Args:
            current_version: 当前版本号
        """
        try:
            for file in os.listdir(self._temp_dir):
                if file.endswith(".zip") and current_version not in file:
                    file_path = os.path.join(self._temp_dir, file)
                    os.remove(file_path)
                    logger.info(f"[UpdateDownloader] 已清理旧版本缓存: {file}")
                    
                    meta_path = self._get_metadata_path(file)
                    if os.path.exists(meta_path):
                        os.remove(meta_path)
                    
                    partial_path = self._get_partial_file_path(file)
                    if os.path.exists(partial_path):
                        os.remove(partial_path)
        except Exception as e:
            logger.warning(f"[UpdateDownloader] 清理旧缓存失败: {e}")
    
    @property
    def downloaded_path(self) -> Optional[str]:
        """获取已下载文件路径"""
        return self._downloaded_path
    
    @property
    def is_downloading(self) -> bool:
        """是否正在下载"""
        return self._is_downloading
    
    @property
    def temp_dir(self) -> str:
        """获取临时目录"""
        return self._temp_dir
