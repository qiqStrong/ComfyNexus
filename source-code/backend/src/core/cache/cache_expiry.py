"""
缓存过期策略工具

提供统一的缓存过期检查和管理功能。
支持从设置中读取自定义 TTL 值。

Author: Comfyui-Box 开发团队
Date: 2026-03-25
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any


class CacheExpiryPolicy:
    """
    缓存过期策略
    
    统一管理缓存的过期时间计算和检查。
    所有缓存模块应使用此策略确保一致的行为。
    """
    
    DEFAULT_TTL_HOURS = 24
    
    def __init__(self, ttl_hours: Optional[float] = None):
        """
        初始化缓存过期策略
        
        Args:
            ttl_hours: 缓存有效期（小时），默认 24 小时
        """
        self.ttl_hours = ttl_hours or self.DEFAULT_TTL_HOURS
        self.ttl_seconds = self.ttl_hours * 3600
    
    def get_current_timestamp(self) -> str:
        """
        获取当前时间戳（ISO 格式）
        
        Returns:
            ISO 格式的时间戳字符串
        """
        return datetime.now().isoformat()
    
    def get_current_unix_timestamp(self) -> float:
        """
        获取当前 Unix 时间戳（秒）
        
        Returns:
            Unix 时间戳
        """
        return datetime.now().timestamp()
    
    def calculate_expires_at(self, created_at: Optional[str] = None) -> str:
        """
        计算过期时间
        
        Args:
            created_at: 创建时间（ISO 格式），默认为当前时间
            
        Returns:
            过期时间（ISO 格式）
        """
        if created_at:
            created = datetime.fromisoformat(created_at)
        else:
            created = datetime.now()
        
        expires_at = created + timedelta(hours=self.ttl_hours)
        return expires_at.isoformat()
    
    def is_expired(
        self,
        created_at: Optional[str] = None,
        expires_at: Optional[str] = None,
        updated_at: Optional[str] = None
    ) -> bool:
        """
        检查缓存是否过期
        
        优先使用 expires_at，其次使用 created_at 或 updated_at。
        
        Args:
            created_at: 创建时间（ISO 格式）
            expires_at: 过期时间（ISO 格式）
            updated_at: 更新时间（ISO 格式，作为 created_at 的别名）
            
        Returns:
            是否过期
        """
        now = datetime.now()
        
        if expires_at:
            try:
                expires = datetime.fromisoformat(expires_at)
                return now > expires
            except (ValueError, TypeError):
                pass
        
        timestamp = created_at or updated_at
        if timestamp:
            try:
                created = datetime.fromisoformat(timestamp)
                age = now - created
                return age > timedelta(hours=self.ttl_hours)
            except (ValueError, TypeError):
                pass
        
        return True
    
    def is_expired_unix(self, timestamp: float) -> bool:
        """
        检查缓存是否过期（Unix 时间戳版本）
        
        Args:
            timestamp: Unix 时间戳（秒）
            
        Returns:
            是否过期
        """
        now = datetime.now().timestamp()
        age = now - timestamp
        return age > self.ttl_seconds
    
    def get_age_hours(self, created_at: str) -> float:
        """
        获取缓存年龄（小时）
        
        Args:
            created_at: 创建时间（ISO 格式）
            
        Returns:
            缓存年龄（小时）
        """
        try:
            created = datetime.fromisoformat(created_at)
            age = datetime.now() - created
            return age.total_seconds() / 3600
        except (ValueError, TypeError):
            return float('inf')
    
    def get_remaining_hours(self, expires_at: str) -> float:
        """
        获取剩余有效时间（小时）
        
        Args:
            expires_at: 过期时间（ISO 格式）
            
        Returns:
            剩余有效时间（小时），已过期返回 0
        """
        try:
            expires = datetime.fromisoformat(expires_at)
            remaining = expires - datetime.now()
            return max(0, remaining.total_seconds() / 3600)
        except (ValueError, TypeError):
            return 0
    
    def add_expiry_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        为缓存数据添加过期相关字段
        
        Args:
            data: 原始缓存数据
            
        Returns:
            添加了过期字段的缓存数据
        """
        now = datetime.now()
        expires = now + timedelta(hours=self.ttl_hours)
        
        data['created_at'] = now.isoformat()
        data['expires_at'] = expires.isoformat()
        data['updated_at'] = now.isoformat()
        data['ttl_hours'] = self.ttl_hours
        
        return data
    
    def update_expiry_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新缓存数据的过期字段
        
        Args:
            data: 缓存数据
            
        Returns:
            更新了过期字段的缓存数据
        """
        now = datetime.now()
        expires = now + timedelta(hours=self.ttl_hours)
        
        data['updated_at'] = now.isoformat()
        data['expires_at'] = expires.isoformat()
        
        if 'created_at' not in data:
            data['created_at'] = now.isoformat()
        
        return data


def get_cache_policy_from_settings(cache_type: str) -> CacheExpiryPolicy:
    """
    从设置中获取缓存过期策略
    
    Args:
        cache_type: 缓存类型 (version/version_dev/translation/plugin/marketplace)
        
    Returns:
        CacheExpiryPolicy 实例
    """
    try:
        from backend.src.core.settings_manager import SettingsManager
        
        settings_manager = SettingsManager()
        cache_settings = settings_manager.get("cache", {})
        
        ttl_mapping = {
            "version": ("versionCacheTtlHours", 24),
            "version_dev": ("versionDevCacheTtlHours", 6),
            "translation": ("translationCacheTtlDays", 30),
            "plugin": ("pluginCacheTtlHours", 24),
            "marketplace": ("marketplaceCacheTtlHours", 24),
        }
        
        if cache_type in ttl_mapping:
            key, default = ttl_mapping[cache_type]
            ttl_value = cache_settings.get(key, default)
            
            if cache_type == "translation":
                ttl_hours = ttl_value * 24
            else:
                ttl_hours = ttl_value
            
            return CacheExpiryPolicy(ttl_hours=ttl_hours)
        
    except Exception:
        pass
    
    return CacheExpiryPolicy()


DEFAULT_CACHE_POLICY = CacheExpiryPolicy(ttl_hours=24)
VERSION_CACHE_POLICY_STABLE = CacheExpiryPolicy(ttl_hours=24)
VERSION_CACHE_POLICY_DEV = CacheExpiryPolicy(ttl_hours=6)
TRANSLATION_CACHE_POLICY = CacheExpiryPolicy(ttl_hours=24 * 30)
PLUGIN_CACHE_POLICY = CacheExpiryPolicy(ttl_hours=24)
MARKETPLACE_CACHE_POLICY = CacheExpiryPolicy(ttl_hours=24)
UPDATE_CACHE_POLICY = CacheExpiryPolicy(ttl_hours=float('inf'))
