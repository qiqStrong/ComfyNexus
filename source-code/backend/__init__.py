"""
Comfyui-Box Backend Package
"""

def get_version():
    """获取版本号（运行时动态获取）"""
    from backend.src.utils.paths import get_version_file
    version_file = get_version_file()
    if version_file.exists():
        try:
            content = version_file.read_text(encoding='utf-8')
            for line in content.splitlines():
                if line.startswith('__version__'):
                    return line.split('=')[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return "1.0.0"

__version__ = get_version()
