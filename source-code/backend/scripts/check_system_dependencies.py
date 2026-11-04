"""
Windows 系统依赖检测工具

检测 Comfyui-Box 运行所需的 Windows 系统组件依赖
"""

import sys
import os
import subprocess
import platform
from pathlib import Path
from typing import NamedTuple
from dataclasses import dataclass, field

# 添加项目路径以导入 subprocess_utils
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from src.utils import subprocess_utils


@dataclass
class CheckResult:
    name: str
    category: str
    passed: bool
    required: bool
    message: str
    details: str = ""


class SystemDependencyChecker:
    def __init__(self):
        self.results: list[CheckResult] = []
        self.passed_count = 0
        self.failed_count = 0
        self.warning_count = 0

    def add_result(self, result: CheckResult):
        self.results.append(result)
        if result.passed:
            self.passed_count += 1
        elif result.required:
            self.failed_count += 1
        else:
            self.warning_count += 1

    def print_header(self, title: str):
        print(f"\n{'='*60}")
        print(f" {title}")
        print(f"{'='*60}")

    def print_result(self, result: CheckResult):
        status = "✅" if result.passed else ("❌" if result.required else "⚠️")
        req_str = "[必需]" if result.required else "[可选]"
        print(f"{status} {req_str} {result.name}: {result.message}")
        if result.details:
            for line in result.details.split("\n"):
                print(f"      {line}")

    def check_windows_version(self):
        self.print_header("系统信息")
        
        try:
            win_version = platform.version()
            win_release = platform.release()
            win_edition = platform.win32_edition() if hasattr(platform, 'win32_edition') else "未知"
            
            print(f"操作系统: Windows {win_release} ({win_edition})")
            print(f"版本号: {win_version}")
            print(f"架构: {platform.machine()}")
            print(f"Python: {sys.version}")
            
            major, minor, build = map(int, win_version.split('.'))
            min_build = 17134
            
            if major >= 10 and build >= min_build:
                self.add_result(CheckResult(
                    name="Windows 版本",
                    category="系统",
                    passed=True,
                    required=True,
                    message=f"Windows 10 1803+ (Build {build})"
                ))
            else:
                self.add_result(CheckResult(
                    name="Windows 版本",
                    category="系统",
                    passed=False,
                    required=True,
                    message=f"版本过低，需要 Windows 10 1803+ (Build {min_build}+)",
                    details=f"当前版本: Build {build}"
                ))
        except Exception as e:
            self.add_result(CheckResult(
                name="Windows 版本",
                category="系统",
                passed=False,
                required=True,
                message=f"检测失败: {e}"
            ))

    def check_system_dlls(self):
        self.print_header("Windows 系统 DLL")
        
        dlls = [
            ("kernel32.dll", True, "进程管理、文件操作"),
            ("user32.dll", True, "窗口管理"),
            ("shell32.dll", True, "Shell 操作、权限检测"),
            ("shcore.dll", True, "DPI 感知"),
            ("gdi32.dll", True, "图形设备接口"),
            ("dwmapi.dll", False, "窗口圆角效果 (Win11)"),
        ]
        
        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        
        for dll_name, required, description in dlls:
            dll_path = system32 / dll_name
            if dll_path.exists():
                try:
                    file_size = dll_path.stat().st_size
                    self.add_result(CheckResult(
                        name=dll_name,
                        category="系统DLL",
                        passed=True,
                        required=required,
                        message=f"存在 ({description})",
                        details=f"路径: {dll_path}, 大小: {file_size:,} bytes"
                    ))
                except Exception as e:
                    self.add_result(CheckResult(
                        name=dll_name,
                        category="系统DLL",
                        passed=False,
                        required=required,
                        message=f"访问失败: {e}"
                    ))
            else:
                self.add_result(CheckResult(
                    name=dll_name,
                    category="系统DLL",
                    passed=False,
                    required=required,
                    message=f"不存在 ({description})",
                    details=f"预期路径: {dll_path}"
                ))

    def check_ctypes_dlls(self):
        self.print_header("ctypes DLL 加载测试")
        
        dll_tests = [
            ("kernel32", "kernel32.dll", True),
            ("user32", "user32.dll", True),
            ("shell32", "shell32.dll", True),
            ("shcore", "shcore.dll", True),
            ("gdi32", "gdi32.dll", True),
            ("dwmapi", "dwmapi.dll", False),
        ]
        
        import ctypes
        
        for attr_name, dll_name, required in dll_tests:
            try:
                dll = getattr(ctypes.windll, attr_name)
                self.add_result(CheckResult(
                    name=f"ctypes.windll.{attr_name}",
                    category="ctypes",
                    passed=True,
                    required=required,
                    message=f"加载成功"
                ))
            except AttributeError as e:
                self.add_result(CheckResult(
                    name=f"ctypes.windll.{attr_name}",
                    category="ctypes",
                    passed=False,
                    required=required,
                    message=f"加载失败: {e}"
                ))
            except Exception as e:
                self.add_result(CheckResult(
                    name=f"ctypes.windll.{attr_name}",
                    category="ctypes",
                    passed=False,
                    required=required,
                    message=f"加载异常: {e}"
                ))

    def check_windows_api_functions(self):
        self.print_header("Windows API 函数测试")
        
        import ctypes
        from ctypes import wintypes
        
        api_tests = [
            ("kernel32", "CreateMutexW", True),
            ("kernel32", "ReleaseMutex", True),
            ("kernel32", "CloseHandle", True),
            ("kernel32", "GetLastError", True),
            ("user32", "FindWindowW", True),
            ("user32", "SetForegroundWindow", True),
            ("user32", "ShowWindow", True),
            ("user32", "GetSystemMetrics", True),
            ("shell32", "IsUserAnAdmin", True),
        ]
        
        for dll_name, func_name, required in api_tests:
            try:
                dll = getattr(ctypes.windll, dll_name)
                func = getattr(dll, func_name)
                self.add_result(CheckResult(
                    name=f"{dll_name}.{func_name}",
                    category="Windows API",
                    passed=True,
                    required=required,
                    message="函数可用"
                ))
            except Exception as e:
                self.add_result(CheckResult(
                    name=f"{dll_name}.{func_name}",
                    category="Windows API",
                    passed=False,
                    required=required,
                    message=f"函数不可用: {e}"
                ))

    def check_powershell(self):
        self.print_header("PowerShell")
        
        ps_path = subprocess_utils.find_powershell()
        if not ps_path:
            self.add_result(CheckResult(
                name="PowerShell",
                category="系统组件",
                passed=False,
                required=True,
                message="未找到 PowerShell 可执行文件"
            ))
            return
        
        try:
            result = subprocess_utils.run_powershell_command(
                "$PSVersionTable.PSVersion.ToString()",
                timeout=10
            )
            
            if result.returncode == 0:
                version = result.stdout.strip()
                self.add_result(CheckResult(
                    name="PowerShell",
                    category="系统组件",
                    passed=True,
                    required=True,
                    message=f"版本 {version} ({Path(ps_path).name})"
                ))
            else:
                self.add_result(CheckResult(
                    name="PowerShell",
                    category="系统组件",
                    passed=False,
                    required=True,
                    message=f"执行失败: {result.stderr.strip()}"
                ))
        except FileNotFoundError:
            self.add_result(CheckResult(
                name="PowerShell",
                category="系统组件",
                passed=False,
                required=True,
                message="未找到 PowerShell"
            ))
        except subprocess.TimeoutExpired:
            self.add_result(CheckResult(
                name="PowerShell",
                category="系统组件",
                passed=False,
                required=True,
                message="执行超时"
            ))
        except Exception as e:
            self.add_result(CheckResult(
                name="PowerShell",
                category="系统组件",
                passed=False,
                required=True,
                message=f"检测异常: {e}"
            ))

    def check_webview2_runtime(self):
        self.print_header("EdgeWebView2 运行时")
        
        import winreg
        
        registry_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        ]
        
        found = False
        version = None
        location = None
        
        for hkey, path in registry_paths:
            try:
                key = winreg.OpenKey(hkey, path)
                try:
                    version, _ = winreg.QueryValueEx(key, "pv")
                    location, _ = winreg.QueryValueEx(key, "location")
                    found = True
                    break
                except FileNotFoundError:
                    pass
                finally:
                    winreg.CloseKey(key)
            except FileNotFoundError:
                continue
            except Exception:
                continue
        
        if found and version:
            self.add_result(CheckResult(
                name="EdgeWebView2 Runtime",
                category="运行时",
                passed=True,
                required=True,
                message=f"版本 {version}",
                details=f"位置: {location}" if location else ""
            ))
        else:
            program_files = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            webview2_path = Path(program_files) / "Microsoft" / "EdgeWebView" / "Application"
            
            if webview2_path.exists():
                versions = list(webview2_path.iterdir())
                if versions:
                    version = versions[0].name
                    self.add_result(CheckResult(
                        name="EdgeWebView2 Runtime",
                        category="运行时",
                        passed=True,
                        required=True,
                        message=f"版本 {version} (通过目录检测)",
                        details=f"路径: {webview2_path}"
                    ))
                    return
            
            self.add_result(CheckResult(
                name="EdgeWebView2 Runtime",
                category="运行时",
                passed=False,
                required=True,
                message="未安装",
                details="请从 https://developer.microsoft.com/en-us/microsoft-edge/webview2/ 下载安装"
            ))

    def check_python_stdlib_modules(self):
        self.print_header("Python 标准库模块")
        
        modules = [
            ("ctypes", True, "Windows API 调用"),
            ("winreg", True, "注册表操作"),
            ("msvcrt", True, "文件锁定"),
            ("subprocess", True, "进程管理"),
            ("threading", True, "多线程"),
            ("json", True, "JSON 处理"),
            ("pathlib", True, "路径处理"),
            ("socket", True, "网络通信"),
            ("ssl", True, "SSL/TLS"),
        ]
        
        for module_name, required, description in modules:
            try:
                __import__(module_name)
                self.add_result(CheckResult(
                    name=module_name,
                    category="标准库",
                    passed=True,
                    required=required,
                    message=f"可用 ({description})"
                ))
            except ImportError as e:
                self.add_result(CheckResult(
                    name=module_name,
                    category="标准库",
                    passed=False,
                    required=required,
                    message=f"不可用: {e}"
                ))

    def check_third_party_packages(self):
        self.print_header("第三方依赖包")
        
        packages = [
            ("pywebview", "webview", True, "GUI 框架"),
            ("psutil", "psutil", True, "系统监控"),
            ("flask", "flask", True, "Web 框架"),
            ("flask_cors", "flask_cors", True, "CORS 支持"),
            ("wmi", "wmi", False, "WMI 接口 (CPU 温度)"),
            ("pythonnet", "clr", False, ".NET 桥接 (LibreHardwareMonitor)"),
            ("pynvml", "pynvml", False, "NVIDIA GPU 监控"),
            ("GPUtil", "GPUtil", False, "GPU 监控"),
            ("PIL", "PIL", False, "图像处理"),
            ("cv2", "cv2", False, "视频处理"),
            ("onnxruntime", "onnxruntime", False, "ONNX 推理"),
        ]
        
        for package_name, import_name, required, description in packages:
            try:
                module = __import__(import_name)
                try:
                    import importlib.metadata
                    version = importlib.metadata.version(package_name)
                except Exception:
                    version = getattr(module, "__version__", "未知版本")
                self.add_result(CheckResult(
                    name=package_name,
                    category="第三方包",
                    passed=True,
                    required=required,
                    message=f"版本 {version} ({description})"
                ))
            except ImportError:
                self.add_result(CheckResult(
                    name=package_name,
                    category="第三方包",
                    passed=False,
                    required=required,
                    message=f"未安装 ({description})"
                ))
            except Exception as e:
                self.add_result(CheckResult(
                    name=package_name,
                    category="第三方包",
                    passed=False,
                    required=required,
                    message=f"加载异常: {e}"
                ))

    def check_admin_privileges(self):
        self.print_header("管理员权限")
        
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if is_admin:
                self.add_result(CheckResult(
                    name="管理员权限",
                    category="权限",
                    passed=True,
                    required=False,
                    message="当前以管理员身份运行",
                    details="硬件传感器监控功能可用"
                ))
            else:
                self.add_result(CheckResult(
                    name="管理员权限",
                    category="权限",
                    passed=False,
                    required=False,
                    message="未以管理员身份运行",
                    details="硬件传感器监控功能将不可用"
                ))
        except Exception as e:
            self.add_result(CheckResult(
                name="管理员权限",
                category="权限",
                passed=False,
                required=False,
                message=f"检测失败: {e}"
            ))

    def check_wmi_service(self):
        self.print_header("WMI 服务")
        
        ps_path = subprocess_utils.find_powershell()
        if not ps_path:
            self.add_result(CheckResult(
                name="WMI 服务",
                category="系统服务",
                passed=False,
                required=False,
                message="PowerShell 不可用，无法检测"
            ))
            return
        
        try:
            result = subprocess_utils.run_powershell_command(
                "Get-Service Winmgmt | Select-Object Status, Name",
                timeout=10
            )
            
            if result.returncode == 0 and "Running" in result.stdout:
                self.add_result(CheckResult(
                    name="WMI 服务",
                    category="系统服务",
                    passed=True,
                    required=False,
                    message="运行中"
                ))
            else:
                self.add_result(CheckResult(
                    name="WMI 服务",
                    category="系统服务",
                    passed=False,
                    required=False,
                    message="未运行或不可用"
                ))
        except Exception as e:
            self.add_result(CheckResult(
                name="WMI 服务",
                category="系统服务",
                passed=False,
                required=False,
                message=f"检测失败: {e}"
            ))

    def print_summary(self):
        self.print_header("检测结果汇总")
        
        total = len(self.results)
        required_results = [r for r in self.results if r.required]
        required_passed = sum(1 for r in required_results if r.passed)
        required_total = len(required_results)
        
        print(f"\n总计检测项: {total}")
        print(f"  ✅ 通过: {self.passed_count}")
        print(f"  ❌ 失败 (必需): {self.failed_count}")
        print(f"  ⚠️  失败 (可选): {self.warning_count}")
        
        print(f"\n必需项: {required_passed}/{required_total}")
        
        if self.failed_count > 0:
            print(f"\n{'='*60}")
            print(" ❌ 以下必需组件检测失败:")
            print(f"{'='*60}")
            for r in self.results:
                if not r.passed and r.required:
                    print(f"  - {r.name}: {r.message}")
                    if r.details:
                        print(f"    {r.details}")
            
            print(f"\n建议操作:")
            print("  1. 确保使用完整版 Windows 系统（非精简版）")
            print("  2. 安装 EdgeWebView2 Runtime: https://developer.microsoft.com/en-us/microsoft-edge/webview2/")
            print("  3. 运行系统文件检查: sfc /scannow")
            print("  4. 安装最新的 Windows 更新")
            
            return False
        else:
            print(f"\n✅ 所有必需组件检测通过！")
            
            if self.warning_count > 0:
                print(f"\n⚠️  以下可选组件未安装（不影响核心功能）:")
                for r in self.results:
                    if not r.passed and not r.required:
                        print(f"  - {r.name}: {r.message}")
            
            return True

    def run(self):
        print("=" * 60)
        print(" Comfyui-Box Windows 系统依赖检测工具")
        print("=" * 60)
        print(f" 检测时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.check_windows_version()
        self.check_system_dlls()
        self.check_ctypes_dlls()
        self.check_windows_api_functions()
        self.check_powershell()
        self.check_webview2_runtime()
        self.check_python_stdlib_modules()
        self.check_third_party_packages()
        self.check_admin_privileges()
        self.check_wmi_service()
        
        return self.print_summary()


def main():
    if sys.platform != "win32":
        print("此工具仅适用于 Windows 系统")
        return 1
    
    checker = SystemDependencyChecker()
    success = checker.run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
