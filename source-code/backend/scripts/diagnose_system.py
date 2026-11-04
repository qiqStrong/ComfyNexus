"""
Comfyui-Box 系统依赖诊断工具 v2.2 (Win10/Win11 专版)
整合了 DLL 检测、Python 包实际调用测试、运行时模拟测试。
自动运行所有测试，无需交互。

使用方式：
  python diagnose_system.py

打包建议 (强烈建议使用 64位 Python 环境打包，防止文件系统重定向导致误报)：
  pyinstaller --onefile --console --name Comfyui-BoxDiag --clean diagnose_system.py
"""

import ctypes
import ctypes.wintypes
import os
import sys
import winreg
import time
import threading
import traceback
from datetime import datetime
from pathlib import Path

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
advapi32 = ctypes.windll.advapi32
gdi32 = ctypes.windll.gdi32

LOAD_LIBRARY_AS_DATAFILE = 0x02
LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x800


class ConsoleColors:
    FOREGROUND_RED = 0x0C
    FOREGROUND_GREEN = 0x0A
    FOREGROUND_YELLOW = 0x0E
    FOREGROUND_CYAN = 0x0B
    FOREGROUND_WHITE = 0x0F
    FOREGROUND_GRAY = 0x07

    @staticmethod
    def _set_color(color):
        handle = kernel32.GetStdHandle(-11)
        if handle:
            kernel32.SetConsoleTextAttribute(handle, color)

    @staticmethod
    def red(): ConsoleColors._set_color(ConsoleColors.FOREGROUND_RED)
    @staticmethod
    def green(): ConsoleColors._set_color(ConsoleColors.FOREGROUND_GREEN)
    @staticmethod
    def yellow(): ConsoleColors._set_color(ConsoleColors.FOREGROUND_YELLOW)
    @staticmethod
    def cyan(): ConsoleColors._set_color(ConsoleColors.FOREGROUND_CYAN)
    @staticmethod
    def white(): ConsoleColors._set_color(ConsoleColors.FOREGROUND_WHITE)
    @staticmethod
    def gray(): ConsoleColors._set_color(ConsoleColors.FOREGROUND_GRAY)
    @staticmethod
    def reset(): ConsoleColors._set_color(ConsoleColors.FOREGROUND_GRAY)


def cprint(text, color_func=None):
    if color_func:
        color_func()
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or 'utf-8'
        print(text.encode(encoding, errors='replace').decode(encoding))
    finally:
        ConsoleColors.reset()


class DiagnosticResult:
    """诊断结果收集器"""
    def __init__(self):
        self.failed_items = []
        self.warning_items = []
        self.passed_count = 0
        self.failed_count = 0
        self.warning_count = 0
    
    def add_pass(self, name):
        self.passed_count += 1
    
    def add_fail(self, name, reason, impact, solution):
        self.failed_count += 1
        self.failed_items.append({
            'name': name,
            'reason': reason,
            'impact': impact,
            'solution': solution
        })
    
    def add_warning(self, name, reason, impact):
        self.warning_count += 1
        self.warning_items.append({
            'name': name,
            'reason': reason,
            'impact': impact
        })


result = DiagnosticResult()


class DLLChecker:
    def __init__(self):
        self.system32 = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32'
        self.syswow64 = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'SysWOW64'
        self.results = []
        self.report_lines = []
        self.total_checks = 0
        self.total_passed = 0
        self.total_failed = 0
        self.total_warnings = 0

    def _try_load_dll(self, dll_name):
        handle = kernel32.LoadLibraryExW(
            dll_name, 0,
            LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_SEARCH_SYSTEM32
        )
        if handle:
            kernel32.FreeLibrary(handle)
            return True, None
        return False, kernel32.GetLastError()

    def _find_dll_path(self, dll_name):
        for search_dir in [self.system32, self.syswow64]:
            dll_path = search_dir / dll_name
            if dll_path.exists():
                return dll_path
        return None

    def _get_file_version(self, file_path):
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        if not file_path.exists():
            return None
        try:
            size = kernel32.GetFileVersionInfoSizeW(str(file_path), None)
            if size == 0: return None
            buffer = ctypes.create_string_buffer(size)
            if not kernel32.GetFileVersionInfoW(str(file_path), 0, size, buffer): return None
            res = ctypes.c_void_p()
            res_len = ctypes.c_uint()
            if not advapi32.VerQueryValueW(buffer, r'\VarFileInfo\Translation', ctypes.byref(res), ctypes.byref(res_len)):
                return None
            trans = ctypes.cast(res, ctypes.POINTER(ctypes.c_uint16))
            lang_id = (trans[0] << 16) | trans[1]
            sub_block = f'\\StringFileInfo\\{lang_id:08X}\\FileVersion'
            if advapi32.VerQueryValueW(buffer, sub_block, ctypes.byref(res), ctypes.byref(res_len)):
                return ctypes.cast(res, ctypes.c_wchar_p).value
        except Exception:
            pass
        return None

    def check_dll(self, dll_name, group_name, severity='P0', description='', impact='', solution=''):
        self.total_checks += 1
        dll_path = self._find_dll_path(dll_name)
        file_exists = dll_path is not None
        can_load, error_code = self._try_load_dll(dll_name)
        version = self._get_file_version(dll_path) if file_exists else None

        result_data = {
            'dll': dll_name, 'group': group_name, 'severity': severity,
            'description': description, 'can_load': can_load, 'file_exists': file_exists
        }
        self.results.append(result_data)

        ver_str = f' v{version}' if version else ''
        if can_load:
            self.total_passed += 1
            result.add_pass(dll_name)
            cprint(f'  [PASS] {dll_name}{ver_str}', ConsoleColors.green)
            self.report_lines.append(f'  [PASS] {dll_name}{ver_str}')
        elif file_exists:
            self.total_warnings += 1
            result.add_warning(dll_name, f'文件存在但损坏 (错误码: 0x{error_code:08X})', impact or f'{description} 可能无法正常工作')
            cprint(f'  [WARN] {dll_name} - 文件存在但损坏 (错误码: 0x{error_code:08X})', ConsoleColors.yellow)
            self.report_lines.append(f'  [WARN] {dll_name} - 文件存在但损坏')
        else:
            self.total_failed += 1
            result.add_fail(dll_name, 'DLL 文件缺失', impact or f'{description} 将无法工作', solution or '运行 sfc /scannow 修复系统')
            cprint(f'  [FAIL] {dll_name} - 缺失!', ConsoleColors.red)
            self.report_lines.append(f'  [FAIL] {dll_name} - 缺失!')
        return result_data

    def _check_group0_webview2(self):
        group_name = 'Edge WebView2 Runtime (P0 级引擎核心)'
        cprint(f'\n[组0] {group_name}', ConsoleColors.cyan)
        self.report_lines.extend([f'\n[组0] {group_name}', '-' * 50])
        self.total_checks += 1

        installed, version = False, None
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")
        ]
        
        for hkey, path in reg_paths:
            try:
                with winreg.OpenKey(hkey, path) as key:
                    version, _ = winreg.QueryValueEx(key, "pv")
                    if version: installed = True; break
            except OSError:
                continue
        
        if not installed:
            fallback = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft' / 'EdgeWebView' / 'Application' / 'msedgewebview2.exe'
            if fallback.exists():
                installed = True
                version = self._get_file_version(fallback) or "未知版本(基于文件)"

        if installed:
            self.total_passed += 1
            result.add_pass('WebView2 Runtime')
            cprint(f'  [PASS] WebView2 Runtime 已安装 (版本: {version})', ConsoleColors.green)
            self.report_lines.append(f'  [PASS] WebView2 Runtime 已安装 (版本: {version})')
        else:
            self.total_failed += 1
            result.add_fail('WebView2 Runtime', 'WebView2 Runtime 未安装', 'Comfyui-Box GUI 界面无法显示，应用将无法启动', '下载: https://go.microsoft.com/fwlink/p/?LinkId=2124703')
            cprint(f'  [FAIL] WebView2 Runtime 未安装!', ConsoleColors.red)
            cprint(f'  影响: Comfyui-Box GUI 界面无法显示，应用将无法启动', ConsoleColors.red)
            cprint(f'  修复: https://go.microsoft.com/fwlink/p/?LinkId=2124703', ConsoleColors.yellow)

    def _check_group1_directx(self):
        group_name = 'DirectX 11 渲染核心 (P0 级白屏元凶)'
        cprint(f'\n[组1] {group_name}', ConsoleColors.cyan)
        self.report_lines.extend([f'\n[组1] {group_name}', '-' * 50])

        dlls = [
            ('d3d11.dll', 'Direct3D 11 核心', 'WebView2 硬件加速失效，可能导致白屏', '运行 sfc /scannow 修复系统'),
            ('dxgi.dll', 'DXGI', 'GPU 适配器枚举失败，可能导致白屏', '运行 sfc /scannow 修复系统'),
            ('d3dcompiler_47.dll', 'HLSL 着色器编译器', '着色器编译失败，渲染异常', '运行 sfc /scannow 修复系统'),
            ('dwmapi.dll', '桌面窗口管理器', '窗口管理异常，圆角/透明效果失效', '运行 sfc /scannow 修复系统')
        ]
        for name, desc, impact, solution in dlls:
            self.check_dll(name, 'DirectX 11', 'P0', desc, impact, solution)

    def _check_group2_ucrt(self):
        group_name = 'Universal C Runtime (P1 级闪退元凶)'
        cprint(f'\n[组2] {group_name}', ConsoleColors.cyan)
        self.report_lines.extend([f'\n[组2] {group_name}', '-' * 50])

        dlls = [
            ('ucrtbase.dll', 'UCRT 主模块', 'Python C 扩展全部崩溃，应用启动闪退', '运行 sfc /scannow 修复系统')
        ]
        for name, desc, impact, solution in dlls:
            self.check_dll(name, 'UCRT', 'P1', desc, impact, solution)

    def _check_group3_vcpp(self):
        group_name = 'VC++ Redistributable 2015-2022'
        cprint(f'\n[组3] {group_name}', ConsoleColors.cyan)
        self.report_lines.extend([f'\n[组3] {group_name}', '-' * 50])

        dlls = [
            ('vcruntime140.dll', 'VC++ Runtime 140', '部分 Python 包无法加载', '下载: https://aka.ms/vs/17/release/vc_redist.x64.exe'),
            ('vcruntime140_1.dll', 'VC++ Runtime 140_1', '部分 Python 包无法加载', '下载: https://aka.ms/vs/17/release/vc_redist.x64.exe'),
            ('msvcp140.dll', 'MSVC++ Standard Library', 'C++ 标准库功能失效', '下载: https://aka.ms/vs/17/release/vc_redist.x64.exe'),
            ('vcomp140.dll', 'VC++ OpenMP Runtime', 'OpenCV 图像处理加速失效', '下载: https://aka.ms/vs/17/release/vc_redist.x64.exe')
        ]
        for name, desc, impact, solution in dlls:
            self.check_dll(name, 'VC++ Redist', 'P0', desc, impact, solution)

    def _check_group4_dotnet(self):
        group_name = '.NET 8 Desktop Runtime'
        cprint(f'\n[组4] {group_name}', ConsoleColors.cyan)
        self.report_lines.extend([f'\n[组4] {group_name}', '-' * 50])
        self.total_checks += 1

        desktop_dir = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'dotnet' / 'shared' / 'Microsoft.WindowsDesktop.App'
        if desktop_dir.exists() and any(d.name.startswith('8.') for d in desktop_dir.iterdir() if d.is_dir()):
            self.total_passed += 1
            result.add_pass('.NET 8 Desktop Runtime')
            cprint(f'  [PASS] .NET 8 Desktop Runtime 已就绪', ConsoleColors.green)
        else:
            self.total_failed += 1
            result.add_fail('.NET 8 Desktop Runtime', '.NET 8 Desktop Runtime 未安装', '硬件监控(LibreHardwareMonitor)将无法工作', '下载: https://aka.ms/dotnet/8.0/windowsdesktop-runtime-win-x64.exe')
            cprint(f'  [FAIL] .NET 8 Desktop Runtime 未安装', ConsoleColors.red)
            cprint(f'  影响: 硬件监控(LibreHardwareMonitor)将无法工作', ConsoleColors.red)
            cprint(f'  修复: https://aka.ms/dotnet/8.0/windowsdesktop-runtime-win-x64.exe', ConsoleColors.yellow)

    def _check_group5_media(self):
        group_name = 'Media Foundation (视频多媒体支持)'
        cprint(f'\n[组5] {group_name}', ConsoleColors.cyan)
        self.report_lines.extend([f'\n[组5] {group_name}', '-' * 50])

        dlls = [
            ('mfplat.dll', 'Media Foundation Platform', '视频播放功能失效 (N版系统)', '安装 Media Feature Pack'),
            ('mf.dll', 'Media Foundation Core', '视频播放功能失效 (N版系统)', '安装 Media Feature Pack')
        ]
        for name, desc, impact, solution in dlls:
            self.check_dll(name, 'Media Foundation', 'P2', desc, impact, solution)

    def _print_summary(self):
        print()
        cprint('=' * 70, ConsoleColors.cyan)
        cprint(f'  DLL 检测汇总 | 通过: {self.total_passed} | 失败: {self.total_failed} | 警告: {self.total_warnings}', ConsoleColors.cyan)
        cprint('=' * 70, ConsoleColors.cyan)

    def run(self):
        cprint(f'\n[阶段 1] 系统核心 DLL 检测', ConsoleColors.cyan)
        self._check_group0_webview2()
        self._check_group1_directx()
        self._check_group2_ucrt()
        self._check_group3_vcpp()
        self._check_group4_dotnet()
        self._check_group5_media()
        self._print_summary()


class PackageCallTester:
    """Python 包实际调用测试器 - 检测包是否损坏"""

    def __init__(self):
        self.total_tests = 0
        self.total_passed = 0
        self.total_failed = 0
        self.total_warnings = 0

    def _test_pil_actual_call(self):
        """PIL 实际调用测试 - 创建图像并操作"""
        group_name = 'PIL/Pillow 实际调用测试'
        cprint(f'\n[包测试 1] {group_name}', ConsoleColors.cyan)
        self.total_tests += 1

        try:
            from PIL import Image, ImageDraw
            
            img = Image.new('RGBA', (100, 100), color=(59, 130, 246, 255))
            
            r, g, b, a = img.getpixel((50, 50))
            if r != 59 or g != 130 or b != 246:
                raise AssertionError(f'像素验证失败: 预期 (59,130,246,255), 实际 ({r},{g},{b},{a})')
            
            draw = ImageDraw.Draw(img)
            draw.rectangle([10, 10, 90, 90], fill=(255, 255, 255, 200))
            
            r2, g2, b2, a2 = img.getpixel((50, 50))
            if r2 != 255 or g2 != 255 or b2 != 255:
                raise AssertionError(f'绘图验证失败: 预期白色, 实际 ({r2},{g2},{b2},{a2})')
            
            img_resized = img.resize((50, 50), Image.Resampling.LANCZOS)
            if img_resized.size != (50, 50):
                raise AssertionError(f'缩放验证失败: 预期 (50,50), 实际 {img_resized.size}')
            
            img_rotated = img.rotate(45)
            
            self.total_passed += 1
            result.add_pass('PIL/Pillow')
            cprint(f'  [PASS] PIL 实际调用成功', ConsoleColors.green)
            cprint(f'  - Image.new() 创建图像成功', ConsoleColors.white)
            cprint(f'  - getpixel() 像素验证成功', ConsoleColors.white)
            cprint(f'  - ImageDraw.Draw() 绘图成功', ConsoleColors.white)
            cprint(f'  - Image.resize() 缩放成功', ConsoleColors.white)
            cprint(f'  - Image.rotate() 旋转成功', ConsoleColors.white)

        except ImportError as e:
            self.total_failed += 1
            result.add_fail('PIL/Pillow', f'导入失败: {e}', '图像处理、托盘图标、缩略图生成全部失效', 'pip install Pillow')
            cprint(f'  [FAIL] PIL 未安装或导入失败: {e}', ConsoleColors.red)
            cprint(f'  影响: 图像处理、托盘图标、缩略图生成全部失效', ConsoleColors.red)
        except AssertionError as e:
            self.total_failed += 1
            result.add_fail('PIL/Pillow', f'功能验证失败: {e}', '图像处理结果不正确，可能影响缩略图等功能', 'pip install --upgrade --force-reinstall Pillow')
            cprint(f'  [FAIL] PIL 功能验证失败: {e}', ConsoleColors.red)
            cprint(f'  影响: 图像处理结果不正确', ConsoleColors.red)
        except Exception as e:
            self.total_failed += 1
            result.add_fail('PIL/Pillow', f'调用异常: {e}', '图像处理功能不稳定', 'pip install --upgrade --force-reinstall Pillow')
            cprint(f'  [FAIL] PIL 实际调用失败: {e}', ConsoleColors.red)
            cprint(f'  影响: 图像处理功能不稳定', ConsoleColors.red)
            for line in traceback.format_exc().split('\n')[-3:]:
                if line.strip():
                    cprint(f'    {line}', ConsoleColors.yellow)

    def _test_pystray_actual_call(self):
        """pystray 实际调用测试 - 创建托盘图标"""
        group_name = 'pystray 实际调用测试'
        cprint(f'\n[包测试 2] {group_name}', ConsoleColors.cyan)
        self.total_tests += 1

        try:
            import pystray
            from PIL import Image
            
            test_icon = Image.new('RGBA', (64, 64), color=(59, 130, 246, 255))
            
            icon = pystray.Icon(
                'Comfyui-BoxDiag_Test',
                test_icon,
                'Comfyui-Box 诊断测试',
                menu=pystray.Menu(
                    pystray.MenuItem('测试菜单项', lambda icon, item: None),
                )
            )
            
            def run_icon():
                try:
                    icon.run()
                except Exception:
                    pass
            
            thread = threading.Thread(target=run_icon, daemon=True)
            thread.start()
            
            time.sleep(1.5)
            
            if icon.visible:
                self.total_passed += 1
                result.add_pass('pystray')
                cprint(f'  [PASS] pystray 实际调用成功', ConsoleColors.green)
                cprint(f'  - pystray.Icon() 创建图标成功', ConsoleColors.white)
                cprint(f'  - pystray.Menu() 创建菜单成功', ConsoleColors.white)
                cprint(f'  - icon.run() 启动成功', ConsoleColors.white)
                cprint(f'  - icon.visible 状态正常', ConsoleColors.white)
                icon.stop()
            else:
                self.total_warnings += 1
                result.add_warning('pystray', '图标创建成功但未显示', '托盘功能可能不稳定')
                cprint(f'  [WARN] pystray 图标未显示', ConsoleColors.yellow)
                cprint(f'  影响: 托盘功能可能不稳定', ConsoleColors.yellow)
                icon.stop()

        except ImportError as e:
            self.total_failed += 1
            result.add_fail('pystray', f'导入失败: {e}', '最小化到托盘功能完全失效', 'pip install pystray')
            cprint(f'  [FAIL] pystray 未安装或导入失败: {e}', ConsoleColors.red)
            cprint(f'  影响: 最小化到托盘功能完全失效', ConsoleColors.red)
        except Exception as e:
            self.total_failed += 1
            result.add_fail('pystray', f'调用异常: {e}', '托盘功能不稳定或失效', 'pip install --upgrade --force-reinstall pystray')
            cprint(f'  [FAIL] pystray 实际调用失败: {e}', ConsoleColors.red)
            cprint(f'  影响: 托盘功能不稳定或失效', ConsoleColors.red)

    def _test_tkinter_actual_call(self):
        """tkinter 实际调用测试 - 创建窗口并操作"""
        group_name = 'tkinter 实际调用测试'
        cprint(f'\n[包测试 3] {group_name}', ConsoleColors.cyan)
        self.total_tests += 1

        try:
            import tkinter as tk
            from tkinter import ttk
            
            root = tk.Tk()
            root.title("tkinter 测试")
            root.geometry("200x150+100+100")
            
            label = tk.Label(root, text="测试标签", font=("Segoe UI", 10))
            label.pack(pady=10)
            
            button = tk.Button(root, text="测试按钮", command=lambda: None)
            button.pack(pady=5)
            
            progress = ttk.Progressbar(root, length=100, mode='determinate')
            progress.pack(pady=5)
            progress['value'] = 50
            
            root.update()
            
            width = root.winfo_width()
            height = root.winfo_height()
            
            root.destroy()
            
            if width > 0 and height > 0:
                self.total_passed += 1
                result.add_pass('tkinter')
                cprint(f'  [PASS] tkinter 实际调用成功', ConsoleColors.green)
                cprint(f'  - tk.Tk() 创建窗口成功', ConsoleColors.white)
                cprint(f'  - tk.Label/Button 创建控件成功', ConsoleColors.white)
                cprint(f'  - ttk.Progressbar 创建进度条成功', ConsoleColors.white)
                cprint(f'  - geometry() 获取尺寸成功: {width}x{height}', ConsoleColors.white)
            else:
                self.total_failed += 1
                result.add_fail('tkinter', f'窗口尺寸异常: {width}x{height}', '预检窗口、安装窗口无法正常显示', '重新安装 Python 或修复 tkinter')
                cprint(f'  [FAIL] tkinter 窗口尺寸异常', ConsoleColors.red)
                cprint(f'  影响: 预检窗口、安装窗口无法正常显示', ConsoleColors.red)

        except ImportError as e:
            self.total_failed += 1
            result.add_fail('tkinter', f'导入失败: {e}', '预检窗口、安装窗口无法显示', '重新安装 Python (确保包含 tkinter)')
            cprint(f'  [FAIL] tkinter 未安装或导入失败: {e}', ConsoleColors.red)
            cprint(f'  影响: 预检窗口、安装窗口无法显示', ConsoleColors.red)
        except Exception as e:
            self.total_failed += 1
            result.add_fail('tkinter', f'调用异常: {e}', 'GUI 窗口功能不稳定', '重新安装 Python')
            cprint(f'  [FAIL] tkinter 实际调用失败: {e}', ConsoleColors.red)
            cprint(f'  影响: GUI 窗口功能不稳定', ConsoleColors.red)

    def _test_ctypes_actual_call(self):
        """ctypes 实际调用测试 - Windows API 调用"""
        group_name = 'ctypes Windows API 实际调用测试'
        cprint(f'\n[包测试 4] {group_name}', ConsoleColors.cyan)
        self.total_tests += 1

        try:
            hdc = user32.GetDC(0)
            if not hdc:
                raise AssertionError('GetDC(0) 返回空')
            
            dpi = gdi32.GetDeviceCaps(hdc, 88)
            user32.ReleaseDC(0, hdc)
            
            screen_width = user32.GetSystemMetrics(0)
            screen_height = user32.GetSystemMetrics(1)
            
            virtual_width = user32.GetSystemMetrics(78)
            virtual_height = user32.GetSystemMetrics(79)
            
            hwnd = user32.GetForegroundWindow()
            
            if dpi <= 0:
                raise AssertionError(f'DPI 值异常: {dpi}')
            if screen_width <= 0 or screen_height <= 0:
                raise AssertionError(f'屏幕尺寸异常: {screen_width}x{screen_height}')
            
            self.total_passed += 1
            result.add_pass('ctypes Windows API')
            cprint(f'  [PASS] ctypes Windows API 调用成功', ConsoleColors.green)
            cprint(f'  - GetDC/ReleaseDC 成功', ConsoleColors.white)
            cprint(f'  - GetDeviceCaps(DPI) = {dpi}', ConsoleColors.white)
            cprint(f'  - GetSystemMetrics(屏幕) = {screen_width}x{screen_height}', ConsoleColors.white)
            cprint(f'  - GetSystemMetrics(虚拟屏幕) = {virtual_width}x{virtual_height}', ConsoleColors.white)

        except AssertionError as e:
            self.total_failed += 1
            result.add_fail('ctypes Windows API', f'验证失败: {e}', 'DPI 感知、窗口操作全部失效', '系统 API 异常，尝试重启或运行 sfc /scannow')
            cprint(f'  [FAIL] Windows API 验证失败: {e}', ConsoleColors.red)
            cprint(f'  影响: DPI 感知、窗口操作全部失效', ConsoleColors.red)
        except Exception as e:
            self.total_failed += 1
            result.add_fail('ctypes Windows API', f'调用异常: {e}', 'DPI 感知、窗口操作全部失效', '系统 API 异常，尝试重启')
            cprint(f'  [FAIL] ctypes 实际调用失败: {e}', ConsoleColors.red)
            cprint(f'  影响: DPI 感知、窗口操作全部失效', ConsoleColors.red)

    def _test_dpi_awareness_actual_call(self):
        """DPI 感知实际设置测试"""
        group_name = 'DPI 感知实际设置测试'
        cprint(f'\n[包测试 5] {group_name}', ConsoleColors.cyan)
        self.total_tests += 1

        try:
            shcore = ctypes.windll.shcore
            
            awareness_before = ctypes.c_int()
            try:
                shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness_before))
                cprint(f'  当前 DPI 感知级别: {awareness_before.value}', ConsoleColors.white)
            except Exception:
                cprint(f'  当前 DPI 感知级别: 无法获取 (可能未设置)', ConsoleColors.white)
            
            try:
                result_code = shcore.SetProcessDpiAwareness(1)
                if result_code == 0:
                    awareness_after = ctypes.c_int()
                    shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness_after))
                    
                    if awareness_after.value >= 1:
                        self.total_passed += 1
                        result.add_pass('DPI 感知设置')
                        cprint(f'  [PASS] DPI 感知设置成功', ConsoleColors.green)
                        cprint(f'  - SetProcessDpiAwareness(1) 返回 0', ConsoleColors.white)
                        cprint(f'  - GetProcessDpiAwareness 返回 {awareness_after.value}', ConsoleColors.white)
                    else:
                        self.total_failed += 1
                        result.add_fail('DPI 感知设置', f'设置后级别仍为 {awareness_after.value}', '窗口四角拖动 resize 可能失效', '系统 DPI 设置异常')
                        cprint(f'  [FAIL] DPI 感知设置后级别仍为 {awareness_after.value}', ConsoleColors.red)
                        cprint(f'  影响: 窗口四角拖动 resize 可能失效', ConsoleColors.red)
                elif result_code == -2147467259:  # E_ACCESSDENIED - 已设置
                    self.total_passed += 1
                    result.add_pass('DPI 感知设置')
                    cprint(f'  [PASS] DPI 感知已设置 (返回 E_ACCESSDENIED 表示已设置)', ConsoleColors.green)
                else:
                    self.total_warnings += 1
                    result.add_warning('DPI 感知设置', f'SetProcessDpiAwareness 返回 {result_code}', '可能已被其他进程设置')
                    cprint(f'  [WARN] SetProcessDpiAwareness 返回 {result_code}', ConsoleColors.yellow)
                    cprint(f'  说明: 可能已被其他进程设置', ConsoleColors.white)
            except Exception as e:
                self.total_warnings += 1
                result.add_warning('DPI 感知设置', f'SetProcessDpiAwareness 异常: {e}', '尝试降级方案')
                cprint(f'  [WARN] SetProcessDpiAwareness 调用异常: {e}', ConsoleColors.yellow)
                cprint(f'  说明: 尝试降级方案...', ConsoleColors.white)
                
                try:
                    user32.SetProcessDPIAware()
                    self.total_passed += 1
                    result.add_pass('DPI 感知设置 (降级)')
                    cprint(f'  [PASS] 降级方案 SetProcessDPIAware 成功', ConsoleColors.green)
                except Exception as e2:
                    self.total_failed += 1
                    result.add_fail('DPI 感知设置', f'降级方案也失败: {e2}', '窗口四角拖动 resize 可能失效', '系统 DPI 设置异常')
                    cprint(f'  [FAIL] 降级方案也失败: {e2}', ConsoleColors.red)
                    cprint(f'  影响: 窗口四角拖动 resize 可能失效', ConsoleColors.red)

        except Exception as e:
            self.total_failed += 1
            result.add_fail('DPI 感知设置', f'测试失败: {e}', '窗口四角拖动 resize 可能失效', '系统 DPI 设置异常')
            cprint(f'  [FAIL] DPI 感知测试失败: {e}', ConsoleColors.red)
            cprint(f'  影响: 窗口四角拖动 resize 可能失效', ConsoleColors.red)

    def _print_summary(self):
        print()
        cprint('=' * 70, ConsoleColors.cyan)
        cprint(f'  包调用测试汇总 | 通过: {self.total_passed} | 失败: {self.total_failed} | 警告: {self.total_warnings}', ConsoleColors.cyan)
        cprint('=' * 70, ConsoleColors.cyan)

    def run(self):
        cprint(f'\n[阶段 2] Python 包实际调用测试', ConsoleColors.cyan)
        self._test_pil_actual_call()
        self._test_pystray_actual_call()
        self._test_tkinter_actual_call()
        self._test_ctypes_actual_call()
        self._test_dpi_awareness_actual_call()
        self._print_summary()


class RuntimeTester:
    """运行时模拟测试器 - 模拟 Comfyui-Box 的窗口操作"""

    def __init__(self):
        self.total_tests = 0
        self.total_passed = 0
        self.total_failed = 0
        self.total_warnings = 0

    def _test_window_resize_simulation(self):
        """模拟窗口 resize 操作，检测坐标转换问题"""
        group_name = '窗口 Resize 模拟测试'
        cprint(f'\n[运行时测试 1] {group_name}', ConsoleColors.cyan)
        self.total_tests += 1

        try:
            import tkinter as tk
            
            root = tk.Tk()
            root.title("Resize 模拟测试")
            root.geometry("300x200+100+100")
            root.overrideredirect(True)
            root.update()
            
            time.sleep(0.1)
            
            new_width = 400
            new_height = 300
            new_x = 50
            new_y = 50
            
            root.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")
            root.update()
            
            time.sleep(0.1)
            
            final_geometry = root.geometry()
            parts = final_geometry.split('+')
            final_size = parts[0].split('x')
            final_x = int(parts[1])
            final_y = int(parts[2])
            final_width = int(final_size[0])
            final_height = int(final_size[1])
            
            root.destroy()
            
            x_diff = abs(final_x - new_x)
            y_diff = abs(final_y - new_y)
            w_diff = abs(final_width - new_width)
            h_diff = abs(final_height - new_height)
            
            if x_diff <= 2 and y_diff <= 2 and w_diff <= 2 and h_diff <= 2:
                self.total_passed += 1
                result.add_pass('窗口 Resize')
                cprint(f'  [PASS] 窗口 resize/move 操作正常', ConsoleColors.green)
                cprint(f'  目标: ({new_x}, {new_y}) {new_width}x{new_height}', ConsoleColors.white)
                cprint(f'  实际: ({final_x}, {final_y}) {final_width}x{final_height}', ConsoleColors.white)
                cprint(f'  偏差: X={x_diff}, Y={y_diff}, W={w_diff}, H={h_diff}', ConsoleColors.white)
            else:
                self.total_failed += 1
                result.add_fail('窗口 Resize', f'偏差过大: X={x_diff}, Y={y_diff}, W={w_diff}, H={h_diff}', '窗口拖动 resize 可能出现漂移问题', 'DPI 缩放转换精度问题')
                cprint(f'  [FAIL] 窗口 resize/move 存在漂移!', ConsoleColors.red)
                cprint(f'  目标: ({new_x}, {new_y}) {new_width}x{new_height}', ConsoleColors.white)
                cprint(f'  实际: ({final_x}, {final_y}) {final_width}x{final_height}', ConsoleColors.white)
                cprint(f'  偏差: X={x_diff}, Y={y_diff}, W={w_diff}, H={h_diff}', ConsoleColors.red)
                cprint(f'  影响: 窗口拖动 resize 可能出现漂移问题', ConsoleColors.red)

        except ImportError:
            self.total_warnings += 1
            result.add_warning('窗口 Resize', 'tkinter 不可用', '无法测试')
            cprint(f'  [WARN] tkinter 不可用，跳过测试', ConsoleColors.yellow)
        except Exception as e:
            self.total_failed += 1
            result.add_fail('窗口 Resize', f'测试异常: {e}', '窗口操作功能异常', '检查系统窗口管理')
            cprint(f'  [FAIL] 测试失败: {e}', ConsoleColors.red)

    def _test_window_show_hide(self):
        """模拟窗口 show/hide 操作，检测恢复问题"""
        group_name = '窗口 Show/Hide 模拟测试'
        cprint(f'\n[运行时测试 2] {group_name}', ConsoleColors.cyan)
        self.total_tests += 1

        try:
            import tkinter as tk
            
            root = tk.Tk()
            root.title("Show/Hide 模拟测试")
            root.geometry("300x200+200+200")
            root.update()
            
            original_x = root.winfo_x()
            original_y = root.winfo_y()
            
            root.withdraw()
            time.sleep(0.2)
            
            root.deiconify()
            root.update()
            time.sleep(0.1)
            
            restored_x = root.winfo_x()
            restored_y = root.winfo_y()
            
            root.destroy()
            
            x_diff = abs(restored_x - original_x)
            y_diff = abs(restored_y - original_y)
            
            if x_diff <= 5 and y_diff <= 5:
                self.total_passed += 1
                result.add_pass('窗口 Show/Hide')
                cprint(f'  [PASS] 窗口 show/hide 后位置正确恢复', ConsoleColors.green)
                cprint(f'  原始: ({original_x}, {original_y})', ConsoleColors.white)
                cprint(f'  恢复: ({restored_x}, {restored_y})', ConsoleColors.white)
            else:
                self.total_failed += 1
                result.add_fail('窗口 Show/Hide', f'位置漂移: X={x_diff}, Y={y_diff}', '从托盘恢复窗口可能位置错误', '需在代码中添加位置保存/恢复逻辑')
                cprint(f'  [FAIL] 窗口 show/hide 后位置漂移!', ConsoleColors.red)
                cprint(f'  原始: ({original_x}, {original_y})', ConsoleColors.white)
                cprint(f'  恢复: ({restored_x}, {restored_y})', ConsoleColors.white)
                cprint(f'  影响: 从托盘恢复窗口可能位置错误', ConsoleColors.red)

        except ImportError:
            self.total_warnings += 1
            result.add_warning('窗口 Show/Hide', 'tkinter 不可用', '无法测试')
            cprint(f'  [WARN] tkinter 不可用，跳过测试', ConsoleColors.yellow)
        except Exception as e:
            self.total_failed += 1
            result.add_fail('窗口 Show/Hide', f'测试异常: {e}', '窗口操作功能异常', '检查系统窗口管理')
            cprint(f'  [FAIL] 测试失败: {e}', ConsoleColors.red)

    def _test_window_foreground(self):
        """测试窗口前台激活能力"""
        group_name = '窗口前台激活测试'
        cprint(f'\n[运行时测试 3] {group_name}', ConsoleColors.cyan)
        self.total_tests += 1

        try:
            import tkinter as tk
            
            root = tk.Tk()
            root.title("前台激活测试窗口")
            root.geometry("300x200+300+300")
            root.update()
            
            hwnd = ctypes.windll.user32.FindWindowW(None, "前台激活测试窗口")
            if hwnd:
                root.withdraw()
                time.sleep(0.2)
                
                root.deiconify()
                root.update()
                
                user32.SetForegroundWindow(hwnd)
                time.sleep(0.1)
                
                foreground_hwnd = user32.GetForegroundWindow()
                
                root.destroy()
                
                if foreground_hwnd == hwnd:
                    self.total_passed += 1
                    result.add_pass('窗口前台激活')
                    cprint(f'  [PASS] SetForegroundWindow 可正常激活窗口', ConsoleColors.green)
                    cprint(f'  说明: 托盘恢复后窗口可正确置于前台', ConsoleColors.white)
                else:
                    self.total_warnings += 1
                    result.add_warning('窗口前台激活', 'SetForegroundWindow 未激活窗口', '托盘恢复后窗口可能不在前台')
                    cprint(f'  [WARN] SetForegroundWindow 未激活窗口', ConsoleColors.yellow)
                    cprint(f'  影响: 托盘恢复后窗口可能不在前台', ConsoleColors.yellow)
                    cprint(f'  原因: Windows 可能阻止非前台进程激活窗口', ConsoleColors.white)
            else:
                self.total_warnings += 1
                result.add_warning('窗口前台激活', '无法获取窗口句柄', '无法测试')
                cprint(f'  [WARN] 无法获取窗口句柄', ConsoleColors.yellow)
                root.destroy()

        except ImportError:
            self.total_warnings += 1
            result.add_warning('窗口前台激活', 'tkinter 不可用', '无法测试')
            cprint(f'  [WARN] tkinter 不可用，跳过测试', ConsoleColors.yellow)
        except Exception as e:
            self.total_warnings += 1
            result.add_warning('窗口前台激活', f'测试异常: {e}', '无法测试')
            cprint(f'  [WARN] 测试异常: {e}', ConsoleColors.yellow)

    def _print_summary(self):
        print()
        cprint('=' * 70, ConsoleColors.cyan)
        cprint(f'  运行时测试汇总 | 通过: {self.total_passed} | 失败: {self.total_failed} | 警告: {self.total_warnings}', ConsoleColors.cyan)
        cprint('=' * 70, ConsoleColors.cyan)

    def run(self):
        cprint(f'\n[阶段 3] 运行时模拟测试', ConsoleColors.cyan)
        cprint('  测试过程中可能会短暂显示测试窗口，请勿操作', ConsoleColors.white)
        
        self._test_window_resize_simulation()
        self._test_window_show_hide()
        self._test_window_foreground()
        self._print_summary()


def print_final_report():
    """打印最终诊断报告"""
    print()
    cprint('=' * 70, ConsoleColors.cyan)
    cprint('                    Comfyui-Box 诊断报告', ConsoleColors.cyan)
    cprint('=' * 70, ConsoleColors.cyan)
    
    total_passed = result.passed_count
    total_failed = result.failed_count
    total_warning = result.warning_count
    
    cprint(f'\n  总体统计: 通过 {total_passed} 项 | 失败 {total_failed} 项 | 警告 {total_warning} 项', ConsoleColors.white)
    
    if result.failed_items:
        cprint('\n  ' + '=' * 66, ConsoleColors.red)
        cprint('  [失败项明细]', ConsoleColors.red)
        cprint('  ' + '=' * 66, ConsoleColors.red)
        for i, item in enumerate(result.failed_items, 1):
            cprint(f'\n  [{i}] {item["name"]}', ConsoleColors.red)
            cprint(f'      原因: {item["reason"]}', ConsoleColors.white)
            cprint(f'      后果: {item["impact"]}', ConsoleColors.yellow)
            cprint(f'      修复: {item["solution"]}', ConsoleColors.green)
    
    if result.warning_items:
        cprint('\n  ' + '=' * 66, ConsoleColors.yellow)
        cprint('  [警告项明细]', ConsoleColors.yellow)
        cprint('  ' + '=' * 66, ConsoleColors.yellow)
        for i, item in enumerate(result.warning_items, 1):
            cprint(f'\n  [{i}] {item["name"]}', ConsoleColors.yellow)
            cprint(f'      原因: {item["reason"]}', ConsoleColors.white)
            cprint(f'      后果: {item["impact"]}', ConsoleColors.yellow)
    
    if not result.failed_items and not result.warning_items:
        cprint('\n  [√] 所有检测项通过，系统环境完美！', ConsoleColors.green)
    
    print()
    cprint('=' * 70, ConsoleColors.cyan)


def main():
    win_ver = sys.getwindowsversion()
    if win_ver.major < 10:
        kernel32.GetStdHandle(-11)
        cprint(f'\n[FATAL ERROR] 您的系统版本为 Windows {win_ver.major}.{win_ver.minor}。', ConsoleColors.red)
        cprint(f'Comfyui-Box 及其诊断工具已停止对 Windows 10 以下版本的支持。', ConsoleColors.red)
        cprint(f'请升级到 Windows 10 或 Windows 11 后再试。', ConsoleColors.red)
        input("\n按回车键退出...")
        return

    cprint(f'\n{"=" * 70}', ConsoleColors.cyan)
    cprint('           Comfyui-Box 深度诊断工具 v2.2', ConsoleColors.cyan)
    cprint(f'{"=" * 70}', ConsoleColors.cyan)
    cprint(f'  系统版本: Windows {win_ver.major}.{win_ver.minor} (Build {win_ver.build})', ConsoleColors.white)
    cprint(f'  诊断时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', ConsoleColors.white)
    cprint(f'  说明: 自动运行所有检测，无需交互', ConsoleColors.gray)
    
    dll_checker = DLLChecker()
    dll_checker.run()
    
    package_tester = PackageCallTester()
    package_tester.run()
    
    runtime_tester = RuntimeTester()
    runtime_tester.run()
    
    print_final_report()
    
    cprint('\n按回车键退出...', ConsoleColors.gray)
    input()


if __name__ == '__main__':
    main()