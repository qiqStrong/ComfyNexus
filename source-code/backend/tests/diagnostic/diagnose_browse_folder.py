"""
诊断文件夹浏览功能
检查当前代码使用的是哪个 API
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.src.bridge.controllers.folder_shortcut_controller import FolderShortcutController
import inspect

print("=" * 80)
print("文件夹浏览功能诊断")
print("=" * 80)

# 获取 browse_folder 方法的源代码
controller = FolderShortcutController()
source = inspect.getsource(controller.browse_folder)

print("\n当前 browse_folder 方法的源代码：")
print("-" * 80)
print(source)
print("-" * 80)

# 检查是否使用了新 API
if "dialog_type=webview.FileDialog.FOLDER" in source:
    print("\n✅ 检测到：使用了新 API（dialog_type=webview.FileDialog.FOLDER）")
    print("   这是正确的实现，性能应该是稳定的。")
elif "webview.FOLDER_DIALOG" in source:
    print("\n❌ 检测到：使用了旧 API（webview.FOLDER_DIALOG）")
    print("   这是旧的实现，可能导致间歇性卡顿。")
    print("   需要更新代码！")
else:
    print("\n⚠️  警告：无法识别使用的 API")
    print("   请手动检查代码。")

print("\n" + "=" * 80)
print("诊断完成")
print("=" * 80)

print("\n重要提示：")
print("1. 如果你运行的是 .exe 文件，需要重新打包才能看到修改效果")
print("2. 打包命令：python -m PyInstaller build_exe.spec --clean")
print("3. 打包后的文件位置：dist/Comfyui-Box.exe")
print("4. 如果是开发模式运行（python backend/main.py），修改应该立即生效")
