"""
统一缓存管理服务

提供统一的缓存管理功能，包括：
- 缓存统计（大小、文件数、更新时间）
- 缓存清理（全部清理、按类型清理）
- 缓存目录管理

Author: Comfyui-Box 开发团队
Date: 2026-03-25
"""

import os
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from backend.src.utils.logger import app_logger as logger
from backend.src.utils.paths import get_cache_dir, get_update_cache_dir


class CacheType(Enum):
    """缓存类型枚举"""
    VERSION = "version"
    TRANSLATION = "translation"
    PLUGIN = "plugin"
    UPDATE = "update"
    MARKETPLACE = "marketplace"


class CacheService:
    """
    统一缓存管理服务
    
    管理所有缓存类型，提供统计和清理功能。
    """
    
    CACHE_TYPE_INFO = {
        CacheType.VERSION: {
            "name": "版本缓存",
            "description": "ComfyUI 版本列表缓存",
            "subdir": "version_list",
        },
        CacheType.TRANSLATION: {
            "name": "翻译缓存",
            "description": "AI 翻译结果缓存",
            "subdir": "",
            "file_pattern": "translation_cache.db",
        },
        CacheType.PLUGIN: {
            "name": "插件缓存",
            "description": "插件和依赖信息缓存",
            "subdir": "plugins",
        },
        CacheType.UPDATE: {
            "name": "更新包缓存",
            "description": "下载的更新包缓存",
            "subdir": "updates",
        },
        CacheType.MARKETPLACE: {
            "name": "市场缓存",
            "description": "插件市场数据缓存",
            "subdir": "marketplace",
        },
    }
    
    def __init__(self):
        """初始化缓存管理服务"""
        self._cache_base_dir = get_cache_dir()
        logger.debug(f"[CacheService] 缓存管理服务已初始化，缓存目录: {self._cache_base_dir}")
    
    def _get_cache_dir(self, cache_type: CacheType) -> Path:
        """
        获取指定类型缓存的目录
        
        Args:
            cache_type: 缓存类型
            
        Returns:
            缓存目录路径
        """
        info = self.CACHE_TYPE_INFO[cache_type]
        subdir = info.get("subdir", "")
        
        if subdir:
            return self._cache_base_dir / subdir
        else:
            return self._cache_base_dir
    
    def _calculate_dir_size(self, dir_path: Path) -> int:
        """
        计算目录大小（字节）
        
        Args:
            dir_path: 目录路径
            
        Returns:
            目录大小（字节）
        """
        if not dir_path.exists():
            return 0
        
        total_size = 0
        try:
            for item in dir_path.rglob("*"):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except (OSError, PermissionError):
                        pass
        except Exception as e:
            logger.warning(f"[CacheService] 计算目录大小失败: {dir_path}, {str(e)}")
        
        return total_size
    
    def _count_files(self, dir_path: Path, pattern: str = "*") -> int:
        """
        统计目录中的文件数量
        
        Args:
            dir_path: 目录路径
            pattern: 文件匹配模式
            
        Returns:
            文件数量
        """
        if not dir_path.exists():
            return 0
        
        try:
            return len(list(dir_path.glob(pattern)))
        except Exception:
            return 0
    
    def _get_latest_mtime(self, dir_path: Path) -> Optional[datetime]:
        """
        获取目录中最新的文件修改时间
        
        Args:
            dir_path: 目录路径
            
        Returns:
            最新修改时间，如果目录不存在或为空则返回 None
        """
        if not dir_path.exists():
            return None
        
        try:
            latest_mtime = None
            for item in dir_path.rglob("*"):
                if item.is_file():
                    try:
                        mtime = datetime.fromtimestamp(item.stat().st_mtime)
                        if latest_mtime is None or mtime > latest_mtime:
                            latest_mtime = mtime
                    except (OSError, PermissionError):
                        pass
            return latest_mtime
        except Exception:
            return None
    
    def _format_size(self, size_bytes: int) -> str:
        """
        格式化文件大小
        
        Args:
            size_bytes: 字节数
            
        Returns:
            格式化后的大小字符串
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    def get_cache_stats(self, cache_type: CacheType) -> Dict:
        """
        获取指定类型缓存的统计信息
        
        Args:
            cache_type: 缓存类型
            
        Returns:
            统计信息字典，包含：
            - type: 缓存类型
            - name: 缓存名称
            - description: 缓存描述
            - size_bytes: 大小（字节）
            - size_formatted: 格式化后的大小
            - file_count: 文件数量
            - last_updated: 最后更新时间
            - path: 缓存路径
        """
        info = self.CACHE_TYPE_INFO[cache_type]
        cache_dir = self._get_cache_dir(cache_type)
        
        file_pattern = info.get("file_pattern", "*")
        
        if file_pattern and file_pattern != "*":
            if cache_dir.joinpath(file_pattern).exists():
                size_bytes = cache_dir.joinpath(file_pattern).stat().st_size
                file_count = 1
                try:
                    last_updated = datetime.fromtimestamp(
                        cache_dir.joinpath(file_pattern).stat().st_mtime
                    )
                except Exception:
                    last_updated = None
            else:
                size_bytes = 0
                file_count = 0
                last_updated = None
        else:
            size_bytes = self._calculate_dir_size(cache_dir)
            file_count = self._count_files(cache_dir, "*.json") + self._count_files(cache_dir, "*.zip")
            file_count += self._count_files(cache_dir, "*.db")
            last_updated = self._get_latest_mtime(cache_dir)
        
        return {
            "type": cache_type.value,
            "name": info["name"],
            "description": info["description"],
            "size_bytes": size_bytes,
            "size_formatted": self._format_size(size_bytes),
            "file_count": file_count,
            "last_updated": last_updated.isoformat() if last_updated else None,
            "path": str(cache_dir),
        }
    
    def get_all_cache_stats(self) -> Dict:
        """
        获取所有缓存的统计信息
        
        Returns:
            包含所有缓存统计信息的字典
        """
        stats_list = []
        total_size = 0
        total_files = 0
        
        for cache_type in CacheType:
            stats = self.get_cache_stats(cache_type)
            stats_list.append(stats)
            total_size += stats["size_bytes"]
            total_files += stats["file_count"]
        
        return {
            "caches": stats_list,
            "total_size_bytes": total_size,
            "total_size_formatted": self._format_size(total_size),
            "total_file_count": total_files,
        }
    
    def clear_cache(self, cache_type: CacheType) -> Dict:
        """
        清理指定类型的缓存
        
        Args:
            cache_type: 缓存类型
            
        Returns:
            清理结果字典
        """
        info = self.CACHE_TYPE_INFO[cache_type]
        cache_dir = self._get_cache_dir(cache_type)
        file_pattern = info.get("file_pattern", "*")
        
        result = {
            "success": False,
            "type": cache_type.value,
            "name": info["name"],
            "cleared_size": 0,
            "cleared_files": 0,
            "error": None,
        }
        
        try:
            if not cache_dir.exists():
                result["success"] = True
                logger.info(f"[CacheService] 缓存目录不存在，无需清理: {cache_dir}")
                return result
            
            cleared_size = 0
            cleared_files = 0
            
            if file_pattern and file_pattern != "*":
                file_path = cache_dir / file_pattern
                if file_path.exists():
                    cleared_size = file_path.stat().st_size
                    file_path.unlink()
                    cleared_files = 1
                    logger.info(f"[CacheService] 已删除缓存文件: {file_path}")
            else:
                for item in cache_dir.iterdir():
                    if item.is_file():
                        try:
                            cleared_size += item.stat().st_size
                            item.unlink()
                            cleared_files += 1
                        except Exception as e:
                            logger.warning(f"[CacheService] 删除文件失败: {item}, {str(e)}")
                    elif item.is_dir():
                        try:
                            dir_size = self._calculate_dir_size(item)
                            cleared_size += dir_size
                            shutil.rmtree(item)
                            cleared_files += 1
                        except Exception as e:
                            logger.warning(f"[CacheService] 删除目录失败: {item}, {str(e)}")
            
            result["success"] = True
            result["cleared_size"] = cleared_size
            result["cleared_files"] = cleared_files
            
            logger.info(
                f"[CacheService] 已清理 {info['name']}: "
                f"{self._format_size(cleared_size)}, {cleared_files} 个文件"
            )
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"[CacheService] 清理缓存失败: {info['name']}, {str(e)}")
        
        return result
    
    def clear_all_caches(self) -> Dict:
        """
        清理所有缓存
        
        Returns:
            清理结果字典
        """
        results = []
        total_cleared_size = 0
        total_cleared_files = 0
        all_success = True
        
        for cache_type in CacheType:
            result = self.clear_cache(cache_type)
            results.append(result)
            total_cleared_size += result.get("cleared_size", 0)
            total_cleared_files += result.get("cleared_files", 0)
            if not result.get("success", False):
                all_success = False
        
        return {
            "success": all_success,
            "results": results,
            "total_cleared_size": total_cleared_size,
            "total_cleared_size_formatted": self._format_size(total_cleared_size),
            "total_cleared_files": total_cleared_files,
        }
    
    def get_cache_types(self) -> List[Dict]:
        """
        获取所有缓存类型信息
        
        Returns:
            缓存类型信息列表
        """
        return [
            {
                "type": cache_type.value,
                "name": info["name"],
                "description": info["description"],
            }
            for cache_type, info in self.CACHE_TYPE_INFO.items()
        ]
