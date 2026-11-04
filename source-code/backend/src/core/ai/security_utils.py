"""
安全工具函数模块

提供 API Key 脱敏、HTTPS 强制和配置验证等安全相关的工具函数。

Author: Comfyui-Box 开发团队
Date: 2025-02-03
"""

from typing import Dict, Any


def mask_api_key(api_key: str) -> str:
    """
    脱敏 API Key，只显示前 4 位和后 4 位，中间用 *** 替代
    
    Args:
        api_key: 原始 API Key
        
    Returns:
        脱敏后的 API Key
        
    Examples:
        >>> mask_api_key("sk-1234567890abcdef")
        'sk-1***cdef'
        >>> mask_api_key("short")
        '***'
        >>> mask_api_key("")
        '***'
        
    Note:
        - 如果 API Key 长度小于 8 位，返回 "***"
        - 如果 API Key 为空或 None，返回 "***"
    """
    if not api_key or len(api_key) < 8:
        return "***"
    
    return f"{api_key[:4]}***{api_key[-4:]}"


def ensure_https(url: str) -> str:
    """
    确保 URL 使用 HTTPS 协议（除了本地开发环境）
    
    自动将 http:// 升级为 https://，但允许本地开发环境使用 HTTP。
    
    Args:
        url: 原始 URL
        
    Returns:
        处理后的 URL（强制 HTTPS 或保持 HTTP for localhost）
        
    Examples:
        >>> ensure_https("http://api.example.com/v1")
        'https://api.example.com/v1'
        >>> ensure_https("https://api.example.com/v1")
        'https://api.example.com/v1'
        >>> ensure_https("http://localhost:8080/api")
        'http://localhost:8080/api'
        >>> ensure_https("http://127.0.0.1:8080/api")
        'http://127.0.0.1:8080/api'
        
    Note:
        - 本地开发环境（localhost, 127.0.0.1, 0.0.0.0）允许使用 HTTP
        - 生产环境强制使用 HTTPS
        - 如果 URL 已经是 HTTPS，保持不变
    """
    if not url:
        return url
    
    # 本地开发环境允许 HTTP
    local_hosts = ["localhost", "127.0.0.1", "0.0.0.0"]
    if any(host in url for host in local_hosts):
        return url
    
    # 生产环境强制 HTTPS
    if url.startswith("http://"):
        return url.replace("http://", "https://", 1)
    
    return url


def validate_config(config: Dict[str, Any]) -> None:
    """
    验证服务商配置参数的有效性
    
    检查 API Key、Base URL 和模型名称等配置项是否符合要求。
    
    Args:
        config: 服务商配置字典，应包含以下字段：
            - api_key: str - API 密钥（必需）
            - base_url: str - API 基础地址（可选）
            - model: str - 模型名称（可选）
            
    Raises:
        ValueError: 当配置参数不符合要求时抛出，包含具体的错误信息
        
    Examples:
        >>> validate_config({"api_key": "sk-1234567890abcdef", "base_url": "https://api.openai.com/v1"})
        # 验证通过，无返回值
        
        >>> validate_config({"api_key": ""})
        Traceback (most recent call last):
            ...
        ValueError: API Key 不能为空
        
        >>> validate_config({"api_key": "short"})
        Traceback (most recent call last):
            ...
        ValueError: API Key 长度不足（至少需要 8 个字符）
        
        >>> validate_config({"api_key": "sk-1234567890abcdef", "base_url": "invalid-url"})
        Traceback (most recent call last):
            ...
        ValueError: Base URL 必须以 http:// 或 https:// 开头
        
    Note:
        - API Key 是必需的，且长度至少为 8 个字符
        - Base URL 如果提供，必须以 http:// 或 https:// 开头
        - 模型名称如果提供，必须是字符串类型
    """
    # 验证 API Key
    if "api_key" not in config or not config["api_key"]:
        raise ValueError("API Key 不能为空")
    
    if not isinstance(config["api_key"], str):
        raise ValueError("API Key 必须是字符串类型")
    
    if len(config["api_key"]) < 8:
        raise ValueError("API Key 长度不足（至少需要 8 个字符）")
    
    # 验证 Base URL（如果提供）
    if "base_url" in config and config["base_url"]:
        base_url = config["base_url"]
        
        if not isinstance(base_url, str):
            raise ValueError("Base URL 必须是字符串类型")
        
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    
    # 验证模型名称（如果提供）
    if "model" in config and config["model"]:
        if not isinstance(config["model"], str):
            raise ValueError("模型名称必须是字符串类型")
