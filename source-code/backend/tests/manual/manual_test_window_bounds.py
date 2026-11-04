"""
窗口边界检查功能测试脚本
用于验证多显示器环境下的窗口位置管理功能

测试说明：
1. 此测试需要在 Comfyui-Box 应用运行时执行
2. 测试会验证窗口边界检查和重置功能
3. 所有操作都在主线程中执行，符合 Windows 线程亲和性要求
"""

import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.src.utils.window_bounds import (
    get_monitor_info,
    get_window_rect,
    check_and_fix_window_bounds,
    reset_window_to_center,
    find_window_by_title
)


def test_window_bounds():
    """测试窗口边界检查功能"""
    print("=" * 60)
    print("窗口边界检查功能测试")
    print("=" * 60)
    
    # 查找窗口
    print("\n[测试 1] 查找 Comfyui-Box 窗口...")
    hwnd = find_window_by_title("Comfyui-Box", max_retries=3, retry_interval=0.5)
    
    if not hwnd or hwnd == 0:
        print("❌ 未找到 Comfyui-Box 窗口")
        print("   请先启动 Comfyui-Box 应用")
        return False
    
    print(f"✓ 找到窗口，句柄: {hwnd}")
    
    # 获取窗口位置
    print("\n[测试 2] 获取窗口位置...")
    window_rect = get_window_rect(hwnd)
    if window_rect:
        left, top, right, bottom = window_rect
        width = right - left
        height = bottom - top
        print(f"✓ 窗口位置: ({left}, {top}, {right}, {bottom})")
        print(f"  窗口尺寸: {width}x{height}")
    else:
        print("❌ 无法获取窗口位置")
        return False
    
    # 获取显示器信息
    print("\n[测试 3] 获取显示器信息...")
    monitor_info = get_monitor_info(hwnd)
    if monitor_info:
        print(f"✓ 显示器信息:")
        print(f"  完整区域: {monitor_info['monitor_rect']}")
        print(f"  工作区域: {monitor_info['work_rect']}")
        print(f"  是否主显示器: {monitor_info['is_primary']}")
        
        work_rect = monitor_info['work_rect']
        work_width = work_rect[2] - work_rect[0]
        work_height = work_rect[3] - work_rect[1]
        print(f"  工作区尺寸: {work_width}x{work_height}")
    else:
        print("❌ 无法获取显示器信息")
        return False
    
    # 测试边界检查
    print("\n[测试 4] 测试边界检查和自动调整...")
    adjusted = check_and_fix_window_bounds(hwnd)
    if adjusted:
        print("✓ 窗口位置已自动调整")
        
        # 再次获取窗口位置
        new_rect = get_window_rect(hwnd)
        if new_rect:
            left, top, right, bottom = new_rect
            width = right - left
            height = bottom - top
            print(f"  调整后位置: ({left}, {top}, {right}, {bottom})")
            print(f"  调整后尺寸: {width}x{height}")
    else:
        print("✓ 窗口位置正常，无需调整")
    
    # 测试重置到中心（带默认尺寸）
    print("\n[测试 5] 测试重置窗口到显示器中心（带默认尺寸）...")
    input("   按 Enter 键继续（将重置窗口到当前显示器中心，并恢复默认尺寸）...")
    
    # 使用默认尺寸 1680x1080
    success = reset_window_to_center(hwnd, default_width=1680, default_height=1080)
    if success:
        print("✓ 窗口已重置到显示器中心")
        
        # 再次获取窗口位置
        new_rect = get_window_rect(hwnd)
        if new_rect:
            left, top, right, bottom = new_rect
            width = right - left
            height = bottom - top
            print(f"  重置后位置: ({left}, {top}, {right}, {bottom})")
            print(f"  重置后尺寸: {width}x{height}")
    else:
        print("❌ 重置窗口位置失败")
        return False
    
    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)
    return True


def test_api_methods():
    """测试 API 方法（需要应用运行时在浏览器控制台执行）"""
    print("\n" + "=" * 60)
    print("API 方法测试说明")
    print("=" * 60)
    print("""
在 Comfyui-Box 应用的浏览器控制台中执行以下代码进行测试：

1. 测试重置窗口位置：
   await window.pywebview.api.resetWindowPosition()
   // 预期：窗口移动到当前显示器中心，并恢复默认尺寸

2. 测试检查窗口边界：
   await window.pywebview.api.checkWindowBounds()
   // 预期：返回 {"success": true, "adjusted": false, "message": "窗口边界正常"}

3. 在窗口获得焦点时自动检查边界（前端代码示例）：
   window.addEventListener('focus', async () => {
       const result = await window.pywebview.api.checkWindowBounds()
       console.log('边界检查结果:', result)
   })
""")


if __name__ == "__main__":
    try:
        print("\n" + "=" * 60)
        print("多显示器窗口边界检查测试")
        print("=" * 60)
        print("\n注意：此测试需要在 Comfyui-Box 应用运行时执行")
        print("      所有操作都在主线程中执行，符合 Windows 线程亲和性要求")
        print()
        
        success = test_window_bounds()
        
        if success:
            test_api_methods()
        
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
