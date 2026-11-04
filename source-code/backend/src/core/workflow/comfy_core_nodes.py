"""
ComfyUI Core 节点列表

从 extension-node-map.json 中提取的 ComfyUI Core 节点列表
用于优先匹配，避免被第三方插件覆盖
"""

import json
import time
from pathlib import Path
from typing import Optional, Set

from backend.src.utils.paths import get_cache_dir
from backend.src.utils.logger import app_logger as logger


COMFY_CORE_NODES_CACHE_FILE = "comfy_core_nodes.json"
COMFY_CORE_GITHUB_URL = "https://github.com/comfyanonymous/ComfyUI"


class ComfyCoreNodesManager:
    """
    ComfyUI Core 节点管理器
    
    管理 ComfyUI Core 的节点列表，用于优先匹配
    """
    
    _instance: Optional['ComfyCoreNodesManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._core_nodes: Set[str] = set()
        self._cache_path: Path = get_cache_dir("marketplace") / COMFY_CORE_NODES_CACHE_FILE
        self._initialized = True
        
        logger.debug("ComfyCoreNodesManager 初始化完成")
    
    def initialize(self, force_refresh: bool = False) -> bool:
        """
        初始化 ComfyUI Core 节点列表
        
        Args:
            force_refresh: 是否强制刷新
            
        Returns:
            是否初始化成功
        """
        if not force_refresh and self._load_from_cache():
            return True
        
        return self.refresh()
    
    def refresh(self) -> bool:
        """
        从远程刷新 ComfyUI Core 节点列表
        
        Returns:
            是否刷新成功
        """
        try:
            import requests
            from backend.src.core.marketplace.constants import NODE_MAP_URL, REQUEST_TIMEOUT
            
            logger.info("正在获取 ComfyUI Core 节点列表...")
            
            url = NODE_MAP_URL
            headers = {'User-Agent': 'Comfyui-Box/1.0'}
            verify_ssl = True
            
            try:
                from backend.src.utils.github_mirror import github_mirror_manager
                if github_mirror_manager.is_enabled():
                    mirror_url, mirror_headers = github_mirror_manager.transform_url(url, "raw")
                    url = mirror_url
                    headers.update(mirror_headers)
                    settings = github_mirror_manager._load_settings()
                    verify_ssl = settings.get("verifySSL", True)
                    logger.dev(f"[ComfyCoreNodes] 使用 raw 镜像源获取节点列表, verify_ssl={verify_ssl}")
            except Exception as e:
                logger.dev(f"[ComfyCoreNodes] 获取镜像设置失败: {e}")
            
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, verify=verify_ssl)
            response.raise_for_status()
            data = response.json()
            
            # 查找 ComfyUI Core 的节点列表
            core_nodes = set()
            for repo_url, node_data in data.items():
                if repo_url.lower() == COMFY_CORE_GITHUB_URL.lower():
                    if isinstance(node_data, list) and len(node_data) > 0:
                        nodes = node_data[0]
                        if isinstance(nodes, list):
                            core_nodes = set(nodes)
                    break
            
            if core_nodes:
                self._core_nodes = core_nodes
                self._save_to_cache()
                logger.info(f"ComfyUI Core 节点列表获取成功：{len(core_nodes)} 个节点")
                return True
            else:
                logger.warning("ComfyUI Core 节点列表为空")
                return False
                
        except Exception as e:
            logger.error(f"获取 ComfyUI Core 节点列表失败: {e}")
            return False
    
    def _load_from_cache(self) -> bool:
        """
        从缓存加载节点列表
        
        Returns:
            是否加载成功
        """
        try:
            if not self._cache_path.exists():
                return False
            
            with open(self._cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._core_nodes = set(data.get('nodes', []))
            
            if self._core_nodes:
                logger.debug(f"从缓存加载 ComfyUI Core 节点列表：{len(self._core_nodes)} 个节点")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"加载 ComfyUI Core 节点缓存失败: {e}")
            return False
    
    def _save_to_cache(self) -> None:
        """
        保存节点列表到缓存
        """
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'timestamp': time.time(),
                'nodes': list(self._core_nodes)
            }
            
            with open(self._cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"ComfyUI Core 节点列表已保存到缓存")
            
        except Exception as e:
            logger.error(f"保存 ComfyUI Core 节点缓存失败: {e}")
    
    def is_core_node(self, node_type: str) -> bool:
        """
        检查节点是否属于 ComfyUI Core
        
        Args:
            node_type: 节点类型
            
        Returns:
            是否是 ComfyUI Core 节点
        """
        return node_type in self._core_nodes
    
    def get_core_nodes(self) -> Set[str]:
        """
        获取所有 ComfyUI Core 节点
        
        Returns:
            ComfyUI Core 节点集合
        """
        return self._core_nodes.copy()


comfy_core_nodes_manager = ComfyCoreNodesManager()
