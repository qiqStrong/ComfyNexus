"""
模型列表缓存管理器

提供基于文件的缓存机制，用于存储从 AI 服务商 API 获取的模型列表。
缓存使用 JSON 格式存储，支持过期时间管理。

缓存目录：<项目根>/cache/ai_models/
缓存文件格式：{provider}_{url_hash}.json

Author: Comfyui-Box 开发团队
Date: 2025-02-03
"""

import hashlib
import json
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
from backend.src.utils.paths import get_cache_dir

logger = logging.getLogger(__name__)


class ModelListCache:
    """模型列表缓存管理器（文件缓存）
    
    使用文件系统存储模型列表缓存，支持过期时间管理。
    每个缓存条目包含模型列表、时间戳、TTL 等信息。
    
    缓存文件结构：
    {
        "models": ["gpt-4", "gpt-3.5-turbo", ...],
        "timestamp": 1707456789.123,
        "ttl": 3600,
        "provider": "openai",
        "base_url": "https://api.openai.com/v1"
    }
    
    Attributes:
        cache_dir: 缓存目录路径
        default_ttl: 默认缓存过期时间（秒）
    """
    
    def __init__(self, cache_dir: Optional[str] = None, default_ttl: int = 3600):
        """初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录路径，None 使用默认路径（<项目根>/cache/ai_models）
            default_ttl: 默认缓存过期时间（秒），默认 1 小时（3600 秒）
        """
        # 使用绝对路径，避免工作目录问题
        if cache_dir is None:
            self.cache_dir = get_cache_dir("ai_models")
        else:
            self.cache_dir = Path(cache_dir)
        
        self.default_ttl = default_ttl
        
        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"初始化缓存管理器: cache_dir={self.cache_dir}, default_ttl={self.default_ttl}")
    
    def get(self, cache_key: str) -> Optional[List[str]]:
        """获取缓存的模型列表
        
        Args:
            cache_key: 缓存键（格式：provider_base_url_hash）
            
        Returns:
            模型列表，如果缓存不存在或已过期则返回 None
            
        Example:
            >>> cache = ModelListCache()
            >>> models = cache.get("openai_a1b2c3d4")
            >>> if models:
            ...     print(f"缓存命中: {models}")
            ... else:
            ...     print("缓存未命中或已过期")
        """
        cache_file = self._get_cache_file_path(cache_key)
        
        # 检查缓存文件是否存在
        if not cache_file.exists():
            logger.debug(f"缓存文件不存在: {cache_file}")
            return None
        
        try:
            # 读取缓存文件
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 验证缓存数据结构
            if not self._validate_cache_data(cache_data):
                logger.warning(f"缓存数据格式无效: {cache_file}")
                return None
            
            # 检查缓存是否过期
            timestamp = cache_data['timestamp']
            ttl = cache_data['ttl']
            current_time = time.time()
            
            if current_time - timestamp > ttl:
                logger.debug(f"缓存已过期: {cache_file}, age={current_time - timestamp:.1f}s, ttl={ttl}s")
                return None
            
            models = cache_data['models']
            logger.debug(f"缓存命中: {cache_key}, models_count={len(models)}")
            return models
            
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.error(f"读取缓存文件失败: {cache_file}, error={str(e)}")
            return None
    
    def set(self, cache_key: str, models: List[str], ttl: Optional[int] = None) -> None:
        """设置缓存
        
        Args:
            cache_key: 缓存键
            models: 模型列表
            ttl: 过期时间（秒），None 使用默认值
            
        Example:
            >>> cache = ModelListCache()
            >>> cache.set("openai_a1b2c3d4", ["gpt-4", "gpt-3.5-turbo"], ttl=3600)
        """
        if ttl is None:
            ttl = self.default_ttl
        
        cache_file = self._get_cache_file_path(cache_key)
        
        # 从缓存键中提取 provider 和 base_url（如果可能）
        # 注意：这里我们只能从缓存键中提取 provider，base_url 已经被哈希
        provider = cache_key.split('_')[0] if '_' in cache_key else "unknown"
        
        cache_data = {
            "models": models,
            "timestamp": time.time(),
            "ttl": ttl,
            "provider": provider,
            "base_url": "hashed"  # 实际的 base_url 已被哈希，这里只是占位
        }
        
        try:
            # 写入缓存文件
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"缓存已更新: {cache_key}, models_count={len(models)}, ttl={ttl}s")
            
        except IOError as e:
            logger.error(f"写入缓存文件失败: {cache_file}, error={str(e)}")
    
    def clear(self, cache_key: Optional[str] = None) -> None:
        """清除缓存
        
        Args:
            cache_key: 缓存键，None 表示清除所有缓存文件
            
        Example:
            >>> cache = ModelListCache()
            >>> cache.clear("openai_a1b2c3d4")  # 清除特定缓存
            >>> cache.clear()  # 清除所有缓存
        """
        if cache_key is None:
            # 清除所有缓存文件
            try:
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink()
                    logger.debug(f"已删除缓存文件: {cache_file}")
                
                logger.info(f"已清除所有缓存文件: {self.cache_dir}")
                
            except IOError as e:
                logger.error(f"清除缓存失败: {str(e)}")
        else:
            # 清除特定缓存文件
            cache_file = self._get_cache_file_path(cache_key)
            
            if cache_file.exists():
                try:
                    cache_file.unlink()
                    logger.debug(f"已删除缓存文件: {cache_file}")
                    
                except IOError as e:
                    logger.error(f"删除缓存文件失败: {cache_file}, error={str(e)}")
            else:
                logger.debug(f"缓存文件不存在，无需删除: {cache_file}")
    
    def generate_cache_key(self, provider: str, base_url: str) -> str:
        """生成缓存键（使用 MD5 哈希避免文件名过长）
        
        Args:
            provider: 服务商名称
            base_url: API 基础 URL
            
        Returns:
            缓存键字符串（格式：provider_hash）
            
        Example:
            >>> cache = ModelListCache()
            >>> key = cache.generate_cache_key("openai", "https://api.openai.com/v1")
            >>> print(key)  # "openai_a1b2c3d4"
        """
        return self._generate_cache_key(provider, base_url)
    
    def _generate_cache_key(self, provider: str, base_url: str) -> str:
        """生成缓存键（内部方法）
        
        使用 MD5 哈希 base_url 以避免文件名过长和特殊字符问题。
        
        Args:
            provider: 服务商名称
            base_url: API 基础 URL
            
        Returns:
            缓存键字符串（格式：provider_hash）
        """
        # 使用 MD5 哈希 base_url，取前 8 位
        url_hash = hashlib.md5(base_url.encode('utf-8')).hexdigest()[:8]
        
        # 组合 provider 和 hash
        cache_key = f"{provider}_{url_hash}"
        
        return cache_key
    
    def _get_cache_file_path(self, cache_key: str) -> Path:
        """获取缓存文件的完整路径
        
        Args:
            cache_key: 缓存键
            
        Returns:
            缓存文件的 Path 对象
        """
        # 确保缓存键是安全的文件名（移除特殊字符）
        safe_cache_key = "".join(c for c in cache_key if c.isalnum() or c in ('_', '-'))
        
        return self.cache_dir / f"{safe_cache_key}.json"
    
    def _validate_cache_data(self, cache_data: Dict[str, Any]) -> bool:
        """验证缓存数据结构是否有效
        
        Args:
            cache_data: 缓存数据字典
            
        Returns:
            True 如果数据结构有效，否则 False
        """
        required_fields = ['models', 'timestamp', 'ttl']
        
        # 检查必需字段是否存在
        for field in required_fields:
            if field not in cache_data:
                return False
        
        # 检查字段类型
        if not isinstance(cache_data['models'], list):
            return False
        
        if not isinstance(cache_data['timestamp'], (int, float)):
            return False
        
        if not isinstance(cache_data['ttl'], int):
            return False
        
        return True
