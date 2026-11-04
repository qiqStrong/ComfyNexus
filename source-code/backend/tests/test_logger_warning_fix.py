"""
测试日志警告修复

验证不再出现 "Logger 'XXX' 尚未通过 setup_logger() 初始化" 的警告
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

print("=" * 60)
print("测试日志警告修复")
print("=" * 60)

print("\n1. 导入 MarketplaceLogger（不应该出现警告）...")
print("-" * 60)

# 导入会触发日志记录器创建的模块
from backend.src.core.marketplace.logger import MarketplaceLogger

print("✓ MarketplaceLogger 导入完成")

print("\n2. 导入 GitPermissionFixer（不应该出现警告）...")
print("-" * 60)

from backend.src.core.plugin.git_permission_fixer import GitPermissionFixer

print("✓ GitPermissionFixer 导入完成")

print("\n2. 初始化日志系统...")
print("-" * 60)

from backend.src.utils.logger import setup_logger

logger = setup_logger(
    name="Comfyui-Box",
    log_dir=None,
    console=True,
    level="DEBUG"
)

print("✓ 日志系统初始化完成")

print("\n3. 使用日志记录器...")
print("-" * 60)

# 使用 MarketplaceLogger
marketplace_logger = MarketplaceLogger()
marketplace_logger.info("这是一条来自 MarketplaceLogger 的测试日志")

# 使用 GitPermissionFixer 中的日志
from backend.src.core.plugin.git_permission_fixer import _get_logger
git_logger = _get_logger()
git_logger.info("这是一条来自 GitPermissionFixer 的测试日志")

print("-" * 60)

print("\n" + "=" * 60)
print("✅ 测试完成！")
print("=" * 60)
print("\n💡 说明：")
print("  - 如果没有看到警告日志，说明修复成功")
print("  - 日志记录器现在是延迟初始化的")
print("  - 只有在实际使用时才会创建日志记录器")
