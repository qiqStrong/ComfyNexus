"""
.NET 运行时管理模块

将 pythonnet 运行时从 .NET Framework (netfx) 切换到 .NET 8 (coreclr)，
消除对系统级 .NET Framework 的依赖。

使用方式：在任何 import webview 之前调用：
    from backend.src.utils.dotnet_runtime import init_dotnet
    init_dotnet()
"""

import json
import os
import sys
import tempfile
import subprocess
from pathlib import Path
from typing import Optional

from .paths import get_internal_dir

# 初始化状态标记
_initialized = False


def _get_creation_flags() -> int:
    """获取适用于当前平台的 creation flags"""
    if sys.platform == "win32" and hasattr(subprocess, 'CREATE_NO_WINDOW'):
        return subprocess.CREATE_NO_WINDOW
    return 0


def _show_fatal_error(message: str, detail: str = "") -> None:
    """用 tkinter 弹出致命错误窗口并退出应用"""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        full_msg = message
        if detail:
            full_msg += f"\n\n{detail}"
        messagebox.showerror("Comfyui-Box - 启动失败", full_msg)
        root.destroy()
    except Exception:
        pass
    sys.exit(1)


def init_dotnet() -> None:
    """
    初始化 .NET 8 coreclr 运行时并替换 WebView2 DLL。
    
    幂等调用：多次调用不会重复初始化。
    必须在任何 import webview / import clr 之前调用。
    如果初始化失败，弹出错误提示后退出应用（edgechromium 后端强制依赖 .NET）。
    """
    global _initialized
    if _initialized:
        return

    if sys.platform != "win32":
        _initialized = True
        return

    try:
        _init_coreclr()
        _preload_assemblies()
        _patch_winforms_compat()
        _patch_webview2_dlls()
        print("[Comfyui-Box] .NET 8 coreclr initialized successfully")
    except Exception as e:
        print(f"[Comfyui-Box] FATAL: .NET 8 init failed: {e}")
        _show_fatal_error(
            ".NET 8 运行时初始化失败，应用无法启动。",
            f"错误信息: {e}\n\n请尝试以下操作:\n"
            "1. 重新安装 .NET 8 Desktop Runtime\n"
            "2. 如果使用 FULL 模式，请确认 runtime/dotnet8/ 目录完整\n"
            "3. 下载地址: https://dotnet.microsoft.com/en-us/download/dotnet/8.0"
        )

    _initialized = True


def _get_project_root() -> Path:
    """获取项目根目录（兼容开发环境和 PyInstaller 打包环境）"""
    return get_internal_dir()


def _find_dotnet_root() -> Optional[Path]:
    """
    定位 .NET 8 Runtime 目录。
    
    查找顺序：
    1. FULL 模式内置 Runtime（runtime/dotnet8/）
    2. 项目内置的 self-contained Runtime（打包环境）
    3. 系统安装的 .NET Runtime
    """
    # 1. FULL 模式：runtime/dotnet8/（用户解压的完整运行时包）
    runtime_dir = os.environ.get('COMFYUI_BOX_RUNTIME_DIR')
    if runtime_dir:
        full_dotnet = Path(runtime_dir) / "dotnet8"
        if full_dotnet.exists() and (full_dotnet / "shared").exists():
            return full_dotnet

    root = _get_project_root()

    # 2. 项目内置 Runtime（打包环境优先）
    bundled = root / "backend" / "lib" / "dotnet8"
    if bundled.exists() and (bundled / "shared").exists():
        return bundled

    # 3. 系统安装的 .NET
    system_dotnet = Path(os.environ.get("ProgramFiles", os.path.join(os.environ.get("SystemDrive", "C:"), "Program Files"))) / "dotnet"
    if system_dotnet.exists():
        # 必须同时有 NETCore.App 和 WindowsDesktop.App 的 8.x 版本
        desktop_app = system_dotnet / "shared" / "Microsoft.WindowsDesktop.App"
        netcore_app = system_dotnet / "shared" / "Microsoft.NETCore.App"

        has_desktop = False
        has_netcore = False

        if desktop_app.exists():
            versions = [d.name for d in desktop_app.iterdir() if d.is_dir() and d.name.startswith("8.")]
            if versions:
                has_desktop = True

        if netcore_app.exists():
            versions = [d.name for d in netcore_app.iterdir() if d.is_dir() and d.name.startswith("8.")]
            if versions:
                has_netcore = True

        if has_desktop and has_netcore:
            return system_dotnet

    return None


def _generate_runtime_config() -> Path:
    """
    生成 runtimeconfig.json 文件。
    
    返回生成的配置文件路径。
    """
    config = {
        "runtimeOptions": {
            "tfm": "net8.0",
            "framework": {
                "name": "Microsoft.WindowsDesktop.App",
                "version": "8.0.0"
            },
            "configProperties": {
                "System.Reflection.Metadata.MetadataUpdater.IsSupported": False
            }
        }
    }

    # 配置文件放在临时目录
    config_dir = Path(tempfile.gettempdir()) / "Comfyui-Box"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "pythonnet.runtimeconfig.json"

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    return config_path


def _init_coreclr() -> None:
    """初始化 coreclr 运行时"""
    import pythonnet

    if pythonnet._LOADED:
        return

    dotnet_root = _find_dotnet_root()
    if dotnet_root is None:
        raise RuntimeError(
            ".NET 8 Desktop Runtime not found.\n"
            "The preflight check should have installed it.\n"
            "Please install manually from:\n"
            "https://dotnet.microsoft.com/en-us/download/dotnet/8.0"
        )

    config_path = _generate_runtime_config()

    try:
        pythonnet.load(
            "coreclr",
            runtime_config=str(config_path),
            dotnet_root=str(dotnet_root),
        )
        
        _setup_assembly_resolve()
        
    except Exception as e:
        raise RuntimeError(
            f"Failed to initialize .NET 8 coreclr runtime.\n"
            f"  dotnet_root: {dotnet_root}\n"
            f"  runtime_config: {config_path}\n"
            f"  Error: {e}"
        ) from e


def _setup_assembly_resolve() -> None:
    """
    注册 AssemblyResolve 事件，处理程序集版本重定向。
    
    解决 LibreHardwareMonitorLib 的依赖项版本不匹配问题：
    - LibreHardwareMonitorLib 需要 System.Threading.AccessControl 10.0.0.0
    - 但实际 DLL 版本可能是 10.0.25.x
    """
    try:
        import System
        from System.Reflection import Assembly
        
        def on_assembly_resolve(sender, args):
            name = args.Name
            
            if name.startswith("System.Threading.AccessControl"):
                root = _get_project_root()
                possible_paths = [
                    root / "lib" / "librehardwaremonitorlib" / "runtimes" / "win-x64" / "lib" / "net8.0" / "System.Threading.AccessControl.dll",
                    root / "lib" / "LibreHardwareMonitor" / "System.Threading.AccessControl.dll",
                    root / "backend" / "lib" / "librehardwaremonitorlib" / "runtimes" / "win-x64" / "lib" / "net8.0" / "System.Threading.AccessControl.dll",
                    root / "backend" / "lib" / "LibreHardwareMonitor" / "System.Threading.AccessControl.dll",
                ]
                for dll_path in possible_paths:
                    if dll_path.exists():
                        return Assembly.LoadFile(str(dll_path))
            
            return None
        
        System.AppDomain.CurrentDomain.AssemblyResolve += on_assembly_resolve
        
    except Exception as e:
        print(f"[Comfyui-Box] AssemblyResolve setup failed: {e}")


def _auto_install_dotnet8() -> None:
    """
    自动下载并安装 .NET 8 Desktop Runtime。
    
    使用 tkinter GUI 窗口显示下载和安装进度，
    风格与 Comfyui-Box 的暗色主题一致。
    tkinter 是 Python 标准库，不依赖 .NET。
    """
    import threading
    import urllib.request
    import ssl

    download_url = "https://aka.ms/dotnet/8.0/windowsdesktop-runtime-win-x64.exe"
    installer_path = Path(tempfile.gettempdir()) / "Comfyui-Box" / "dotnet8-desktop-runtime.exe"
    installer_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        # tkinter 不可用，回退到 CMD 方式
        _auto_install_dotnet8_cmd()
        return

    # ========== tkinter GUI ==========
    root = tk.Tk()
    root.title("Comfyui-Box")
    root.geometry("480x320")
    root.resizable(False, False)
    root.configure(bg="#1e1e2e")

    # 居中显示
    root.update_idletasks()
    x = (root.winfo_screenwidth() - 480) // 2
    y = (root.winfo_screenheight() - 320) // 2
    root.geometry(f"480x320+{x}+{y}")

    # 去掉默认标题栏的白色边框效果
    root.overrideredirect(False)

    # 颜色定义
    BG = "#1e1e2e"
    FG = "#e4e4e7"
    ACCENT = "#7c3aed"
    ACCENT_LIGHT = "#a78bfa"
    DIM = "#71717a"
    SUCCESS = "#22c55e"
    ERROR = "#ef4444"

    # 标题
    tk.Label(root, text="Comfyui-Box", font=("Segoe UI", 18, "bold"),
             fg=ACCENT_LIGHT, bg=BG).pack(pady=(30, 5))

    # 副标题
    tk.Label(root, text=".NET 8 Desktop Runtime Required",
             font=("Segoe UI", 10), fg=DIM, bg=BG).pack(pady=(0, 20))

    # 状态文本
    status_var = tk.StringVar(value="Preparing download...")
    status_label = tk.Label(root, textvariable=status_var,
                            font=("Segoe UI", 10), fg=FG, bg=BG)
    status_label.pack(pady=(0, 10))

    # 进度条
    style = ttk.Style()
    style.theme_use('default')
    style.configure("Custom.Horizontal.TProgressbar",
                    troughcolor="#27273a", background=ACCENT,
                    darkcolor=ACCENT, lightcolor=ACCENT_LIGHT,
                    bordercolor=BG, thickness=8)

    progress = ttk.Progressbar(root, length=380, mode='determinate',
                                style="Custom.Horizontal.TProgressbar")
    progress.pack(pady=(0, 8))

    # 进度文本
    progress_text_var = tk.StringVar(value="")
    tk.Label(root, textvariable=progress_text_var,
             font=("Segoe UI", 9), fg=DIM, bg=BG).pack(pady=(0, 15))

    # 底部提示
    hint_var = tk.StringVar(value="Downloading from Microsoft official server...")
    tk.Label(root, textvariable=hint_var,
             font=("Segoe UI", 9), fg=DIM, bg=BG).pack(side=tk.BOTTOM, pady=15)

    # 下载安装逻辑（在后台线程运行）
    install_success = [False]

    def do_download_install():
        try:
            # 下载
            status_var.set("Downloading .NET 8 Desktop Runtime...")

            ctx = ssl.create_default_context()
            req = urllib.request.Request(download_url, headers={"User-Agent": "Comfyui-Box/1.0"})
            try:
                resp = urllib.request.urlopen(req, context=ctx, timeout=300)
            except ssl.SSLError:
                ctx = ssl._create_unverified_context()
                resp = urllib.request.urlopen(req, context=ctx, timeout=300)

            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 256 * 1024

            with open(installer_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded * 100 / total
                        mb = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        progress['value'] = pct
                        progress_text_var.set(f"{mb:.1f} / {total_mb:.1f} MB ({pct:.0f}%)")
            resp.close()

            # 验证文件大小
            file_size = installer_path.stat().st_size
            if file_size < 40 * 1024 * 1024:
                status_var.set("Download failed - file too small")
                status_label.configure(fg=ERROR)
                hint_var.set("Please download manually: https://dotnet.microsoft.com/download/dotnet/8.0")
                return

            # 安装
            progress['value'] = 100
            progress_text_var.set("")
            status_var.set("Installing .NET 8 Desktop Runtime...")
            hint_var.set("This may take a minute, please wait...")

            result = subprocess.run(
                [str(installer_path), "/install", "/quiet", "/norestart"],
                capture_output=True, text=True, timeout=300,
                creationflags=_get_creation_flags(),
            )

            if result.returncode in (0, 1641, 3010, 1638):
                install_success[0] = True
                status_var.set("Installation complete!")
                status_label.configure(fg=SUCCESS)
                hint_var.set("Comfyui-Box will continue starting...")
            else:
                status_var.set(f"Installation returned code {result.returncode}")
                status_label.configure(fg=ERROR)
                hint_var.set("Please try installing manually")

        except Exception as e:
            status_var.set(f"Error: {str(e)[:60]}")
            status_label.configure(fg=ERROR)
            hint_var.set("Please download manually: https://dotnet.microsoft.com/download/dotnet/8.0")
        finally:
            # 清理安装包
            if installer_path.exists():
                try:
                    installer_path.unlink()
                except Exception:
                    pass
            # 延迟关闭窗口
            root.after(2000 if install_success[0] else 5000, root.destroy)

    # 启动后台线程
    thread = threading.Thread(target=do_download_install, daemon=True)
    thread.start()

    # 运行 GUI 主循环（阻塞直到窗口关闭）
    try:
        root.mainloop()
    except Exception:
        pass


def _auto_install_dotnet8_cmd() -> None:
    """CMD 回退方案：tkinter 不可用时弹 CMD 窗口"""
    installer_dir = Path(tempfile.gettempdir()) / "Comfyui-Box"
    installer_dir.mkdir(parents=True, exist_ok=True)
    installer_path = installer_dir / "dotnet8-desktop-runtime.exe"
    script_path = installer_dir / "_install_dotnet8.bat"

    bat_content = f'''@echo off
chcp 65001 >nul 2>nul
title Comfyui-Box - Installing .NET 8 Runtime
color 0B
echo.
echo  ============================================================
echo   Comfyui-Box - .NET 8 Desktop Runtime Installer
echo  ============================================================
echo.
echo   Downloading from Microsoft...
echo.
set "URL=https://aka.ms/dotnet/8.0/windowsdesktop-runtime-win-x64.exe"
set "OUT={installer_path}"
where powershell >nul 2>nul
if %errorlevel% equ 0 (
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '%URL%' -OutFile '%OUT%' -UseBasicParsing"
    if %errorlevel% equ 0 goto :install
)
certutil -urlcache -split -f "%URL%" "%OUT%" >nul 2>nul
if %errorlevel% equ 0 goto :install
echo   [ERROR] Download failed.
pause
exit /b 1
:install
echo   Installing...
"%OUT%" /install /quiet /norestart
echo   Done. This window will close in 3 seconds.
del "%OUT%" >nul 2>nul
timeout /t 3 /nobreak >nul
'''
    script_path.write_text(bat_content, encoding="utf-8")
    try:
        subprocess.run(["cmd", "/c", str(script_path)],
                       creationflags=subprocess.CREATE_NEW_CONSOLE, timeout=600)
    except Exception:
        pass
    finally:
        for f in [script_path, installer_path]:
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass



def _find_webview2_netcore_dir() -> Optional[Path]:
    """定位 netcoreapp3.0 版本的 WebView2 DLL 目录"""
    root = _get_project_root()

    # 项目内置
    netcore_dir = root / "backend" / "lib" / "webview2_netcore"
    if netcore_dir.exists():
        core_dll = netcore_dir / "Microsoft.Web.WebView2.Core.dll"
        winforms_dll = netcore_dir / "Microsoft.Web.WebView2.WinForms.dll"
        if core_dll.exists() and winforms_dll.exists():
            return netcore_dir

    return None


def _preload_assemblies() -> None:
    """
    预加载 .NET 8 下需要显式引用的程序集。
    
    在 .NET Framework 下，很多类型包含在 System.dll 中，不需要显式 AddReference。
    但在 .NET 8 (coreclr) 下，这些类型被拆分到独立程序集中，
    pywebview 的 winforms.py 在 import 时会因为找不到类型而失败。
    """
    import clr

    # Microsoft.Win32.SystemEvents — winforms.py 第 27 行需要
    # .NET Framework 下在 System.dll 中，.NET 8 下是独立程序集
    try:
        clr.AddReference("Microsoft.Win32.SystemEvents")
    except Exception:
        pass

    # System.Drawing.Primitives — 确保 Color, Point, Size 等类型可用
    try:
        clr.AddReference("System.Drawing.Primitives")
    except Exception:
        pass

    # System.Drawing.Common — Icon, ColorTranslator 等
    try:
        clr.AddReference("System.Drawing.Common")
    except Exception:
        pass

    # System.ComponentModel.Primitives — 部分 WinForms 控件依赖
    try:
        clr.AddReference("System.ComponentModel.Primitives")
    except Exception:
        pass

    # System.Threading.AccessControl — LibreHardwareMonitor 需要
    # Mutex 构造函数的 MutexSecurity 重载在 .NET 8 下需要此程序集
    try:
        clr.AddReference("System.Threading.AccessControl")
    except Exception:
        pass


def _patch_winforms_compat() -> None:
    """
    修复 pywebview winforms.py 中与 .NET 8 不兼容的代码。
    
    需要修复两个问题：
    1. _is_chromium() 检查 .NET Framework 注册表键，精简版 Windows 没有 .NET Framework
       导致返回 False，回退到 MSHTML
    2. OpenFolderDialog 使用反射访问 .NET Framework 内部类型，.NET 8 下不存在
    
    采用双重机制：
    1. 优先修改 .py 源码（开发环境有效）
    2. 如果源码不存在（打包环境），使用运行时 monkey-patch
    """
    try:
        import webview
        winforms_path = Path(webview.__file__).parent / "platforms" / "winforms.py"

        if winforms_path.exists():
            source = winforms_path.read_text(encoding="utf-8")

            if "# PATCHED_FOR_DOTNET8" in source:
                return

            modified = False

            old_is_chromium = "is_chromium = not is_cef and _is_chromium() and forced_gui_ != 'mshtml'"
            new_is_chromium = "is_chromium = not is_cef and (forced_gui_ == 'edgechromium' or _is_chromium()) and forced_gui_ != 'mshtml'  # PATCHED_FOR_DOTNET8"
            if old_is_chromium in source:
                source = source.replace(old_is_chromium, new_is_chromium)
                modified = True

            if "FileDialogNative+IFileDialog" in source:
                marker = "class OpenFolderDialog:"
                if marker in source:
                    idx = source.index(marker)
                    rest = source[idx:]
                    lines = rest.split('\n')
                    end_line = len(lines)
                    for i, line in enumerate(lines[1:], 1):
                        stripped = line.strip()
                        if line and not line[0].isspace() and stripped and not stripped.startswith('#'):
                            end_line = i
                            break

                    replacement = '''class OpenFolderDialog:  # PATCHED_FOR_DOTNET8
    """Folder dialog compatible with .NET 8
    
    修复：使用 Invoke 将 FolderBrowserDialog.ShowDialog 封送到 UI 线程执行。
    原因：pywebview 的 js_bridge_call 在 MTA 线程上调用 API 方法，
    而 FolderBrowserDialog 底层依赖 Windows Shell COM 接口（IShellFolder），
    要求 STA 线程环境。在 MTA 线程上直接调用 ShowDialog 会导致：
    - 对话框不弹出（COM 初始化失败）
    - 对话框弹出但无法关联父窗口（被遮挡）
    - 对话框死锁等待 UI 线程消息
    通过 parent.Invoke() 将调用封送到 UI 线程（STA），与 OpenFileDialog /
    SaveFileDialog 的 ShowDialog(parent) 行为保持一致。
    """
    foldersFilter = 'Folders|\\n'

    @classmethod
    def show(cls, parent=None, initialDirectory=None, allow_multiple=False, title=None):
        dialog = WinForms.FolderBrowserDialog()
        if initialDirectory:
            dialog.SelectedPath = initialDirectory
        if title:
            dialog.Description = title

        def _show_dialog():
            return dialog.ShowDialog(parent)

        if parent and parent.InvokeRequired:
            result = parent.Invoke(Func[Type](_show_dialog))
        elif parent:
            result = _show_dialog()
        else:
            result = dialog.ShowDialog()

        if result == WinForms.DialogResult.OK:
            return (dialog.SelectedPath,)
        return None

'''
                    source = source[:idx] + replacement + '\n'.join(lines[end_line:])
                    modified = True

            if modified:
                winforms_path.write_text(source, encoding="utf-8")
                pycache = winforms_path.parent / "__pycache__"
                if pycache.exists():
                    import shutil
                    shutil.rmtree(str(pycache), ignore_errors=True)

    except Exception as e:
        print(f"[Comfyui-Box] Cannot patch winforms.py: {e}")


def _apply_winforms_monkey_patches() -> None:
    """
    运行时 monkey-patch winforms 模块中的 OpenFolderDialog。
    
    在打包环境下 .py 源文件不存在，源码 patch 无法执行，
    因此需要在模块加载后直接替换类定义。
    """
    try:
        import logging
        _logger = logging.getLogger('Comfyui-Box')
        
        from webview.platforms import winforms as wf
        if getattr(wf, '_dotnet8_patched', False):
            _logger.info("[OpenFolderDialog] monkey-patch: 已应用，跳过")
            return

        has_winforms = hasattr(wf, 'WinForms')
        has_func = hasattr(wf, 'Func')
        _logger.info(f"[OpenFolderDialog] monkey-patch: WinForms={has_winforms}, Func={has_func}")

        if has_winforms and has_func:
            _orig_show = getattr(wf.OpenFolderDialog, 'show', None)
            
            class PatchedOpenFolderDialog:
                """Folder dialog compatible with .NET 8"""
                foldersFilter = 'Folders|\n'

                @classmethod
                def show(cls, parent=None, initialDirectory=None, allow_multiple=False, title=None):
                    _logger.info(f"[OpenFolderDialog.show] 被调用: parent={parent}, initialDirectory={initialDirectory}")
                    try:
                        dialog = wf.WinForms.FolderBrowserDialog()
                        if initialDirectory:
                            import os
                            abs_dir = os.path.abspath(initialDirectory)
                            if os.path.isdir(abs_dir):
                                dialog.SelectedPath = abs_dir
                                _logger.info(f"[OpenFolderDialog.show] SelectedPath={abs_dir}")
                            else:
                                _logger.warning(f"[OpenFolderDialog.show] initialDirectory 不存在: {initialDirectory} (abs={abs_dir}), 跳过设置")
                        if title:
                            dialog.Description = title

                        def _show_dialog():
                            return dialog.ShowDialog(parent)

                        _logger.info(f"[OpenFolderDialog.show] InvokeRequired={parent.InvokeRequired if parent else 'N/A'}")
                        if parent and parent.InvokeRequired:
                            _logger.info("[OpenFolderDialog.show] 使用 Invoke 封送到 UI 线程")
                            _result_holder = [None]
                            def _show_and_capture():
                                _result_holder[0] = dialog.ShowDialog(parent)
                            from System import Action
                            parent.Invoke(Action(_show_and_capture))
                            result = _result_holder[0]
                        elif parent:
                            _logger.info("[OpenFolderDialog.show] 直接调用 ShowDialog(parent)")
                            result = _show_dialog()
                        else:
                            _logger.info("[OpenFolderDialog.show] 直接调用 ShowDialog()")
                            result = dialog.ShowDialog()

                        _logger.info(f"[OpenFolderDialog.show] ShowDialog 返回: {result}")
                        if result == wf.WinForms.DialogResult.OK:
                            return (dialog.SelectedPath,)
                        return None
                    except Exception as e:
                        _logger.error(f"[OpenFolderDialog.show] 异常: {e}", exc_info=True)
                        return None

            wf.OpenFolderDialog = PatchedOpenFolderDialog
            wf._dotnet8_patched = True
            _logger.info("[OpenFolderDialog] monkey-patch applied for .NET 8 compatibility")
        else:
            _logger.warning(f"[OpenFolderDialog] monkey-patch: 条件不满足 (WinForms={has_winforms}, Func={has_func})，跳过")
    except Exception as e:
        import logging as _logging
        _logging.getLogger('Comfyui-Box').error(f"[OpenFolderDialog] monkey-patch 异常: {e}", exc_info=True)


def _patch_gpu_args(hardware_acceleration: bool = True) -> None:
    """
    根据 GPU 设置在 AdditionalBrowserArguments 中注入参数。

    采用双重机制确保在所有环境下生效：
    1. 优先修改 pywebview 源码 (edgechromium.py)，最可靠的方式
    2. 如果源码不存在（打包环境只有 .pyc），使用运行时 monkey-patch
       —— 在 EdgeChrome.__init__ 返回后、EnsureCoreWebView2Async 异步完成前
       修改 CreationProperties.AdditionalBrowserArguments

    Args:
        hardware_acceleration: 是否启用硬件加速，默认 True
    """
    try:
        from backend.src.ui.webview2_diagnostic import is_safe_mode

        # 安全模式强制禁用 GPU，优先级最高
        disable_gpu = is_safe_mode() or not hardware_acceleration

        if not disable_gpu:
            return

        import webview

        edgechromium_path = Path(webview.__file__).parent / "platforms" / "edgechromium.py"
        if edgechromium_path.exists():
            source = edgechromium_path.read_text(encoding="utf-8")

            if "--disable-gpu" not in source:
                target = "props.AdditionalBrowserArguments = '--disable-features=ElasticOverscroll'"
                replacement = "props.AdditionalBrowserArguments = '--disable-features=ElasticOverscroll --disable-gpu --disable-gpu-compositing'  # GPU_PATCHED"

                if target in source:
                    source = source.replace(target, replacement)
                    edgechromium_path.write_text(source, encoding="utf-8")
                    pycache = edgechromium_path.parent / "__pycache__"
                    if pycache.exists():
                        for pyc in pycache.iterdir():
                            if pyc.name.startswith("edgechromium.") and pyc.suffix == ".pyc":
                                try:
                                    pyc.unlink()
                                except OSError:
                                    pass
                    print("[Comfyui-Box] GPU args patch applied to edgechromium.py")
                    return

        from webview.platforms.edgechromium import EdgeChrome
        if getattr(EdgeChrome, '_gpu_args_patched', False):
            return

        _original_init = EdgeChrome.__init__

        def _patched_init(self, *args, **kwargs):
            _original_init(self, *args, **kwargs)
            try:
                current = self.webview.CreationProperties.AdditionalBrowserArguments or ''
                if '--disable-gpu' not in current:
                    self.webview.CreationProperties.AdditionalBrowserArguments = current + ' --disable-gpu --disable-gpu-compositing'
            except Exception:
                pass

        EdgeChrome.__init__ = _patched_init
        EdgeChrome._gpu_args_patched = True
        print("[Comfyui-Box] GPU args patch applied via monkey-patch")

    except Exception as e:
        print(f"[Comfyui-Box] Cannot apply GPU args patch: {e}")


def _patch_webview2_dlls() -> None:
    """
    将 netcoreapp3.0 版本的 WebView2 DLL 复制到 pywebview 的 lib/ 目录，
    覆盖 net462 版本。
    
    这比 monkey-patch interop_dll_path 更可靠，因为：
    1. PyInstaller 打包后模块可能被冻结，monkey-patch 时机不对
    2. edgechromium.py 在 import 时就调用 interop_dll_path，是模块级别执行
    3. 直接覆盖文件让原始的 interop_dll_path 找到正确的 DLL
    """
    import shutil

    netcore_dir = _find_webview2_netcore_dir()
    if netcore_dir is None:
        return

    try:
        import webview
        webview_lib = Path(webview.__file__).parent / "lib"

        if not webview_lib.exists():
            return

        dlls_to_replace = [
            "Microsoft.Web.WebView2.Core.dll",
            "Microsoft.Web.WebView2.WinForms.dll",
        ]

        for dll_name in dlls_to_replace:
            src = netcore_dir / dll_name
            dst = webview_lib / dll_name

            if not src.exists():
                continue

            # 检查是否已经是 netcoreapp3.0 版本（通过文件大小判断）
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                continue

            # 覆盖为 netcoreapp3.0 版本（不创建 .bak 备份，避免被 PyInstaller 收集）
            try:
                shutil.copy2(str(src), str(dst))
            except PermissionError:
                pass
            except Exception:
                pass

    except ImportError:
        pass


def _ensure_webview2_runtime() -> None:
    """
    检测 WebView2 Runtime 是否已安装，未安装则自动下载安装。
    
    WebView2 Runtime 是 Edge 浏览器内核的独立运行时，
    pywebview edgechromium 后端需要它来渲染网页。
    Evergreen Bootstrapper 只有约 1.7MB，下载很快。
    """
    if _check_webview2_installed():
        return

    _auto_install_webview2()


def _check_webview2_installed() -> bool:
    """检查 WebView2 Runtime 是否已安装"""
    import winreg

    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
    ]

    for hkey, path in registry_paths:
        try:
            key = winreg.OpenKey(hkey, path)
            version, _ = winreg.QueryValueEx(key, "pv")
            winreg.CloseKey(key)
            if version and version != "0.0.0.0":
                return True
        except (FileNotFoundError, OSError):
            continue

    # 回退：检查文件系统
    webview2_path = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft" / "EdgeWebView" / "Application"
    if webview2_path.exists():
        versions = [d for d in webview2_path.iterdir() if d.is_dir()]
        if versions:
            return True

    return False


def _auto_install_webview2() -> None:
    """
    自动下载并安装 WebView2 Runtime。
    
    使用 tkinter GUI 显示进度，回退到 CMD。
    Evergreen Bootstrapper 约 1.7MB，会自动下载完整 Runtime。
    """
    import urllib.request
    import ssl

    # WebView2 Evergreen Bootstrapper（约 1.7MB，会自动下载完整 Runtime）
    download_url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
    installer_path = Path(tempfile.gettempdir()) / "Comfyui-Box" / "MicrosoftEdgeWebview2Setup.exe"
    installer_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        _auto_install_webview2_cmd()
        return

    # ========== tkinter GUI ==========
    root = tk.Tk()
    root.title("Comfyui-Box")
    root.geometry("480x280")
    root.resizable(False, False)
    root.configure(bg="#1e1e2e")

    root.update_idletasks()
    x = (root.winfo_screenwidth() - 480) // 2
    y = (root.winfo_screenheight() - 280) // 2
    root.geometry(f"480x280+{x}+{y}")

    BG = "#1e1e2e"
    FG = "#e4e4e7"
    ACCENT = "#7c3aed"
    ACCENT_LIGHT = "#a78bfa"
    DIM = "#71717a"
    SUCCESS = "#22c55e"
    ERROR = "#ef4444"

    tk.Label(root, text="Comfyui-Box", font=("Segoe UI", 18, "bold"),
             fg=ACCENT_LIGHT, bg=BG).pack(pady=(30, 5))

    tk.Label(root, text="WebView2 Runtime Required",
             font=("Segoe UI", 10), fg=DIM, bg=BG).pack(pady=(0, 20))

    status_var = tk.StringVar(value="Downloading WebView2 Runtime...")
    status_label = tk.Label(root, textvariable=status_var,
                            font=("Segoe UI", 10), fg=FG, bg=BG)
    status_label.pack(pady=(0, 10))

    style = ttk.Style()
    style.theme_use('default')
    style.configure("WV2.Horizontal.TProgressbar",
                    troughcolor="#27273a", background=ACCENT,
                    darkcolor=ACCENT, lightcolor=ACCENT_LIGHT,
                    bordercolor=BG, thickness=8)

    progress = ttk.Progressbar(root, length=380, mode='indeterminate',
                                style="WV2.Horizontal.TProgressbar")
    progress.pack(pady=(0, 15))
    progress.start(15)

    hint_var = tk.StringVar(value="Bootstrapper is small (~1.7 MB), full runtime downloads automatically")
    tk.Label(root, textvariable=hint_var,
             font=("Segoe UI", 9), fg=DIM, bg=BG).pack(side=tk.BOTTOM, pady=15)

    import threading
    install_success = [False]

    def do_install():
        try:
            # 下载 Bootstrapper
            ctx = ssl.create_default_context()
            req = urllib.request.Request(download_url, headers={"User-Agent": "Comfyui-Box/1.0"})
            try:
                resp = urllib.request.urlopen(req, context=ctx, timeout=120)
            except ssl.SSLError:
                ctx = ssl._create_unverified_context()
                resp = urllib.request.urlopen(req, context=ctx, timeout=120)

            with open(installer_path, "wb") as f:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            resp.close()

            # 安装
            status_var.set("Installing WebView2 Runtime...")
            hint_var.set("This may take a minute...")

            result = subprocess.run(
                [str(installer_path), "/silent", "/install"],
                capture_output=True, text=True, timeout=300,
                creationflags=_get_creation_flags(),
            )

            if result.returncode == 0:
                install_success[0] = True
                status_var.set("WebView2 Runtime installed!")
                status_label.configure(fg=SUCCESS)
                hint_var.set("Comfyui-Box will continue starting...")
            else:
                status_var.set(f"Installer returned code {result.returncode}")
                status_label.configure(fg=ERROR)
                hint_var.set("Please try installing manually")

        except Exception as e:
            status_var.set(f"Error: {str(e)[:60]}")
            status_label.configure(fg=ERROR)
            hint_var.set("Download: https://developer.microsoft.com/en-us/microsoft-edge/webview2/")
        finally:
            progress.stop()
            if installer_path.exists():
                try:
                    installer_path.unlink()
                except Exception:
                    pass
            root.after(2000 if install_success[0] else 5000, root.destroy)

    thread = threading.Thread(target=do_install, daemon=True)
    thread.start()

    try:
        root.mainloop()
    except Exception:
        pass


def _auto_install_webview2_cmd() -> None:
    """CMD 回退方案"""

    installer_dir = Path(tempfile.gettempdir()) / "Comfyui-Box"
    installer_dir.mkdir(parents=True, exist_ok=True)
    installer_path = installer_dir / "MicrosoftEdgeWebview2Setup.exe"
    script_path = installer_dir / "_install_webview2.bat"

    bat = f'''@echo off
chcp 65001 >nul 2>nul
title Comfyui-Box - Installing WebView2 Runtime
color 0B
echo.
echo  Comfyui-Box - WebView2 Runtime Installer
echo.
echo  Downloading WebView2 Bootstrapper...
set "URL=https://go.microsoft.com/fwlink/p/?LinkId=2124703"
set "OUT={installer_path}"
where powershell >nul 2>nul
if %errorlevel% equ 0 (
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '%URL%' -OutFile '%OUT%' -UseBasicParsing"
    if %errorlevel% equ 0 goto :install
)
certutil -urlcache -split -f "%URL%" "%OUT%" >nul 2>nul
if %errorlevel% equ 0 goto :install
echo  [ERROR] Download failed.
pause
exit /b 1
:install
echo  Installing WebView2 Runtime...
"%OUT%" /silent /install
echo  Done.
del "%OUT%" >nul 2>nul
timeout /t 3 /nobreak >nul
'''
    script_path.write_text(bat, encoding="utf-8")
    try:
        subprocess.run(["cmd", "/c", str(script_path)],
                       creationflags=subprocess.CREATE_NEW_CONSOLE, timeout=300)
    except Exception:
        pass
    finally:
        for f in [script_path, installer_path]:
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
