"""
插件备份工具

提供插件更新前的备份和失败时的回滚功能。
参考核心版本管理(backend/updater/updater.py)的备份机制实现。
"""

import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from backend.src.utils.logger import app_logger as logger
from backend.src.utils.file_utils import force_remove_directory


BACKUP_EXCLUDE_PATTERNS = [
    '.git',           # Git 仓库目录(太大,且可通过 Git 恢复)
    '__pycache__',    # Python 缓存目录
    'node_modules',   # Node.js 依赖目录(如果有)
    '.pytest_cache',  # pytest 缓存
    '.mypy_cache',    # mypy 缓存
    '*.pyc',          # Python 编译文件
    '*.pyo',          # Python 优化编译文件
    '*.pyd',          # Python 动态链接库
    '.DS_Store',      # macOS 系统文件
    'Thumbs.db',      # Windows 缩略图缓存
]

BACKUP_DIR_NAME = 'Comfyui-Box_Plugin_Backups'
MAX_BACKUP_COUNT = 10  # 保留最近10个备份


def _should_exclude(path: Path) -> bool:
    """
    检查路径是否应该被排除
    
    Args:
        path: 要检查的路径
        
    Returns:
        True: 应该排除
        False: 不应该排除
    """
    name = path.name
    
    for pattern in BACKUP_EXCLUDE_PATTERNS:
        if pattern.startswith('*'):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern:
            return True
    
    return False


def _get_backup_base_dir() -> Path:
    """
    获取备份基础目录
    
    Returns:
        备份基础目录路径
    """
    return Path(tempfile.gettempdir()) / BACKUP_DIR_NAME


def backup_plugin(plugin_path: Path) -> Optional[Path]:
    """
    备份单个插件目录
    
    Args:
        plugin_path: 插件目录路径
        
    Returns:
        备份目录路径,失败返回 None
    """
    try:
        if not plugin_path.exists() or not plugin_path.is_dir():
            logger.error(f"[PluginBackup] 插件目录不存在或不是目录: {plugin_path}")
            return None
        
        plugin_name = plugin_path.name
        timestamp = int(time.time())
        
        backup_base = _get_backup_base_dir()
        backup_base.mkdir(parents=True, exist_ok=True)
        
        backup_dir = backup_base / f"backup_{timestamp}_{plugin_name}"
        
        logger.info(f"[PluginBackup] 开始备份插件: {plugin_name} -> {backup_dir}")
        
        copied_count = 0
        skipped_count = 0
        
        for item in plugin_path.rglob('*'):
            if _should_exclude(item):
                skipped_count += 1
                continue
            
            if item.is_file():
                rel_path = item.relative_to(plugin_path)
                dst_file = backup_dir / rel_path
                
                try:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dst_file)
                    copied_count += 1
                except PermissionError as pe:
                    logger.warning(f"[PluginBackup] 权限错误,跳过: {rel_path} - {pe}")
                    skipped_count += 1
                except Exception as e:
                    logger.warning(f"[PluginBackup] 复制失败,跳过: {rel_path} - {e}")
                    skipped_count += 1
        
        logger.info(
            f"[PluginBackup] 备份完成: {plugin_name}, "
            f"复制 {copied_count} 个文件, 跳过 {skipped_count} 个文件"
        )
        
        cleanup_old_backups()
        
        return backup_dir
        
    except Exception as e:
        logger.error(f"[PluginBackup] 备份失败: {plugin_path.name} - {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def restore_plugin(backup_path: Path, plugin_path: Path) -> bool:
    """
    从备份恢复插件
    
    Args:
        backup_path: 备份目录路径
        plugin_path: 插件目录路径
        
    Returns:
        是否成功恢复
    """
    try:
        if not backup_path.exists() or not backup_path.is_dir():
            logger.error(f"[PluginBackup] 备份目录不存在: {backup_path}")
            return False
        
        plugin_name = plugin_path.name
        logger.info(f"[PluginBackup] 开始恢复插件: {backup_path} -> {plugin_path}")
        
        if plugin_path.exists():
            logger.debug(f"[PluginBackup] 删除现有插件目录: {plugin_path}")
            try:
                force_remove_directory(plugin_path)
            except Exception as e:
                logger.warning(f"[PluginBackup] 删除插件目录失败: {e}")
                return False
        
        plugin_path.mkdir(parents=True, exist_ok=True)
        
        restored_count = 0
        failed_count = 0
        
        for item in backup_path.rglob('*'):
            if item.is_file():
                rel_path = item.relative_to(backup_path)
                dst_file = plugin_path / rel_path
                
                try:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dst_file)
                    restored_count += 1
                except PermissionError as pe:
                    logger.warning(f"[PluginBackup] 权限错误,跳过: {rel_path} - {pe}")
                    failed_count += 1
                except Exception as e:
                    logger.warning(f"[PluginBackup] 恢复失败,跳过: {rel_path} - {e}")
                    failed_count += 1
        
        logger.info(
            f"[PluginBackup] 恢复完成: {plugin_name}, "
            f"恢复 {restored_count} 个文件, 失败 {failed_count} 个文件"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"[PluginBackup] 恢复失败: {backup_path} -> {plugin_path} - {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def cleanup_backup(backup_path: Path) -> bool:
    """
    清理单个备份目录
    
    Args:
        backup_path: 备份目录路径
        
    Returns:
        是否成功清理
    """
    try:
        if not backup_path.exists():
            return True
        
        force_remove_directory(backup_path)
        logger.debug(f"[PluginBackup] 清理备份: {backup_path}")
        return True
        
    except Exception as e:
        logger.warning(f"[PluginBackup] 清理备份失败: {backup_path} - {e}")
        return False


def cleanup_old_backups(max_count: int = MAX_BACKUP_COUNT) -> int:
    """
    清理旧备份,只保留最近的几个
    
    Args:
        max_count: 保留的最大备份数量
        
    Returns:
        清理的备份数量
    """
    try:
        backup_base = _get_backup_base_dir()
        
        if not backup_base.exists():
            return 0
        
        backups = sorted(
            backup_base.glob('backup_*'),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        cleaned_count = 0
        for old_backup in backups[max_count:]:
            try:
                force_remove_directory(old_backup)
                logger.debug(f"[PluginBackup] 清理旧备份: {old_backup.name}")
                cleaned_count += 1
            except Exception as e:
                logger.warning(f"[PluginBackup] 清理旧备份失败: {old_backup} - {e}")
        
        if cleaned_count > 0:
            logger.info(f"[PluginBackup] 清理了 {cleaned_count} 个旧备份")
        
        return cleaned_count
        
    except Exception as e:
        logger.error(f"[PluginBackup] 清理旧备份失败: {e}")
        return 0


def get_backup_info(backup_path: Path) -> Optional[dict]:
    """
    获取备份信息
    
    Args:
        backup_path: 备份目录路径
        
    Returns:
        备份信息字典,失败返回 None
    """
    try:
        if not backup_path.exists():
            return None
        
        stat = backup_path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        
        parts = backup_path.name.split('_', 2)
        timestamp = int(parts[1]) if len(parts) >= 2 else 0
        plugin_name = parts[2] if len(parts) >= 3 else "unknown"
        
        file_count = sum(1 for _ in backup_path.rglob('*') if _.is_file())
        
        return {
            'path': str(backup_path),
            'plugin_name': plugin_name,
            'timestamp': timestamp,
            'created_at': mtime.isoformat(),
            'file_count': file_count,
            'size': stat.st_size,
        }
        
    except Exception as e:
        logger.error(f"[PluginBackup] 获取备份信息失败: {backup_path} - {e}")
        return None


def list_all_backups() -> List[dict]:
    """
    列出所有备份
    
    Returns:
        备份信息列表
    """
    try:
        backup_base = _get_backup_base_dir()
        
        if not backup_base.exists():
            return []
        
        backups = []
        for backup_dir in backup_base.glob('backup_*'):
            info = get_backup_info(backup_dir)
            if info:
                backups.append(info)
        
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return backups
        
    except Exception as e:
        logger.error(f"[PluginBackup] 列出备份失败: {e}")
        return []
