"""
Comfyui-Box Bridge 插件模块

提供 ComfyUI 自定义节点桥接插件
"""

from .get_plugin_content import get_bridge_plugin_version, get_plugin_content

__all__ = ['get_plugin_content', 'get_bridge_plugin_version']
