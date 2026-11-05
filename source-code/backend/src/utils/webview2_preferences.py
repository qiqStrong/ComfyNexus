"""
WebView2 Preferences 文件管理工具

该模块用于读取和修改 WebView2 的 Preferences 文件，
特别是用于同步下载路径记忆功能。
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from backend.src.utils.logger import app_logger as logger


class WebView2PreferencesManager:
    """WebView2 Preferences 文件管理器"""
    
    @staticmethod
    def _resolve_default_preferences_path() -> Path:
        """解析当前 WebView2 用户数据目录中的 Preferences 文件路径。"""
        user_data_folder = os.environ.get('WEBVIEW2_USER_DATA_FOLDER')
        if user_data_folder:
            user_data_dir = Path(user_data_folder)
            candidates = [
                user_data_dir / "EBWebView" / "Default" / "Preferences",
                user_data_dir / "Default" / "Preferences",
            ]
            for candidate in candidates:
                if candidate.exists():
                    return candidate
            return candidates[0]

        # 降级路径使用机器级 WebView2 数据目录，供未显式设置时使用。
        from backend.src.utils.paths import get_webview2_dir
        return get_webview2_dir() / "EBWebView" / "Default" / "Preferences"

    def __init__(self, preferences_path: Optional[str] = None):
        """
        初始化 Preferences 管理器
        
        Args:
            preferences_path: Preferences 文件路径，如果为 None 则使用默认路径
        """
        if preferences_path is None:
            preferences_path = self._resolve_default_preferences_path()
        
        self.preferences_path = Path(preferences_path)
        logger.debug(f"[WebView2 Preferences] 初始化管理器，路径: {self.preferences_path}")
    
    def _read_preferences(self) -> Optional[Dict[str, Any]]:
        """
        读取 Preferences 文件
        
        Returns:
            dict: Preferences 内容，如果读取失败则返回 None
        """
        try:
            if not self.preferences_path.exists():
                logger.warning(f"[WebView2 Preferences] 文件不存在: {self.preferences_path}")
                return None
            
            with open(self.preferences_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.debug(f"[WebView2 Preferences] 成功读取文件")
            return data
        
        except json.JSONDecodeError as e:
            logger.error(f"[WebView2 Preferences] JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"[WebView2 Preferences] 读取文件失败: {e}")
            return None
    
    def _write_preferences(self, data: Dict[str, Any]) -> bool:
        """
        写入 Preferences 文件
        
        Args:
            data: 要写入的数据
            
        Returns:
            bool: 是否写入成功
        """
        try:
            # 确保目录存在
            self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件（不格式化，保持原始格式）
            with open(self.preferences_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            
            logger.debug(f"[WebView2 Preferences] 成功写入文件")
            return True
        
        except Exception as e:
            logger.error(f"[WebView2 Preferences] 写入文件失败: {e}")
            return False
    
    def get_last_download_directory(self) -> Optional[str]:
        """
        获取上次下载目录
        
        Returns:
            str: 上次下载目录路径，如果不存在则返回 None
        """
        try:
            data = self._read_preferences()
            if not data:
                return None
            
            # 读取 selectfile.last_directory
            last_dir = data.get('selectfile', {}).get('last_directory')
            
            if last_dir:
                logger.info(f"[WebView2 Preferences] 读取到上次下载目录: {last_dir}")
            else:
                logger.debug(f"[WebView2 Preferences] 未找到上次下载目录")
            
            return last_dir
        
        except Exception as e:
            logger.error(f"[WebView2 Preferences] 获取下载目录失败: {e}")
            return None
    
    def set_last_download_directory(self, directory: str) -> bool:
        """
        设置上次下载目录
        
        Args:
            directory: 目录路径（可以是文件路径，会自动提取目录）
            
        Returns:
            bool: 是否设置成功
        """
        try:
            # 如果传入的是文件路径，提取目录
            if os.path.isfile(directory) or (not os.path.isdir(directory) and os.path.splitext(directory)[1]):
                directory = os.path.dirname(directory)
                logger.debug(f"[WebView2 Preferences] 从文件路径提取目录: {directory}")
            
            # 标准化路径（使用反斜杠，与 Windows 一致）
            directory = os.path.abspath(directory).replace('/', '\\')
            
            logger.info(f"[WebView2 Preferences] 设置下载目录: {directory}")
            
            # 读取现有数据
            data = self._read_preferences()
            if data is None:
                logger.warning(f"[WebView2 Preferences] 无法读取现有数据，创建新数据")
                data = {}
            
            # 确保 selectfile 键存在
            if 'selectfile' not in data:
                data['selectfile'] = {}
            
            # 更新 last_directory
            data['selectfile']['last_directory'] = directory
            
            # 写入文件
            success = self._write_preferences(data)
            
            if success:
                logger.info(f"[WebView2 Preferences] ✅ 成功更新下载目录")
            else:
                logger.error(f"[WebView2 Preferences] ❌ 更新下载目录失败")
            
            return success
        
        except Exception as e:
            logger.error(f"[WebView2 Preferences] 设置下载目录失败: {e}")
            import traceback
            logger.debug(f"[WebView2 Preferences] 错误堆栈:\n{traceback.format_exc()}")
            return False
    
    def sync_from_file_path(self, file_path: str) -> bool:
        """
        从文件路径同步下载目录到 Preferences
        
        这是一个便捷方法，用于在用户选择文件后自动同步路径。
        
        Args:
            file_path: 用户选择的文件完整路径
            
        Returns:
            bool: 是否同步成功
        """
        return self.set_last_download_directory(file_path)
