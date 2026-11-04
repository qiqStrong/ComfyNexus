"""
启动预检模块

在应用启动前检测所有外部依赖，缺失时弹出 tkinter GUI 引导用户一键安装。
全部通过时静默返回，不打扰用户。

使用方式：在 init_dotnet() 之前调用：
    from backend.src.utils.preflight import run_preflight
    run_preflight()
"""

import ctypes
import os
import sys
import subprocess
import tempfile
import threading
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Callable

from .paths import get_mingit_dir


def _get_creation_flags() -> int:
    """获取适用于当前平台的 creation flags"""
    if sys.platform == "win32" and hasattr(subprocess, 'CREATE_NO_WINDOW'):
        return subprocess.CREATE_NO_WINDOW
    return 0


@dataclass
class PreflightItem:
    """预检项"""
    name: str           # 显示名称
    passed: bool        # 是否通过
    version: str        # 版本信息或缺失提示
    install_url: str    # 下载地址（空字符串表示不支持自动安装）
    install_args: list  # 安装命令参数
    size_hint: str      # 安装包大小提示


# ============================================================
#  检测函数
# ============================================================

def check_dotnet8() -> PreflightItem:
    """检测 .NET 8 Desktop Runtime"""
    name = ".NET 8 Desktop Runtime"
    system_dotnet = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "dotnet"

    # 必须同时有 NETCore.App 和 WindowsDesktop.App 的 8.x 版本
    netcore_app = system_dotnet / "shared" / "Microsoft.NETCore.App"
    desktop_app = system_dotnet / "shared" / "Microsoft.WindowsDesktop.App"

    netcore_ok = False
    desktop_ok = False
    version = ""

    if netcore_app.exists():
        versions = [d.name for d in netcore_app.iterdir() if d.is_dir() and d.name.startswith("8.")]
        if versions:
            netcore_ok = True
            version = sorted(versions)[-1]

    if desktop_app.exists():
        versions = [d.name for d in desktop_app.iterdir() if d.is_dir() and d.name.startswith("8.")]
        if versions:
            desktop_ok = True
            if not version:
                version = sorted(versions)[-1]

    if netcore_ok and desktop_ok:
        return PreflightItem(name, True, version, "", [], "")

    # 部分安装或完全缺失
    detail = "Not installed"
    if desktop_ok and not netcore_ok:
        detail = "Incomplete (NETCore.App missing)"
    elif netcore_ok and not desktop_ok:
        detail = "Incomplete (WindowsDesktop.App missing)"

    return PreflightItem(
        name, False, detail,
        "https://aka.ms/dotnet/8.0/windowsdesktop-runtime-win-x64.exe",
        ["/install", "/passive", "/norestart"],
        "~55 MB",
    )


def check_webview2() -> PreflightItem:
    """检测 WebView2 Runtime"""
    name = "Edge WebView2 Runtime"
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
    ]
    for hkey, path in reg_paths:
        try:
            key = winreg.OpenKey(hkey, path)
            ver, _ = winreg.QueryValueEx(key, "pv")
            winreg.CloseKey(key)
            if ver and ver != "0.0.0.0":
                return PreflightItem(name, True, ver, "", [], "")
        except (FileNotFoundError, OSError):
            continue

    return PreflightItem(
        name, False, "Not installed",
        "https://go.microsoft.com/fwlink/p/?LinkId=2124703",
        ["/silent", "/install"],
        "~1.7 MB bootstrapper",
    )


def check_vcruntime() -> PreflightItem:
    """检测 VC++ Runtime 2015-2022"""
    name = "VC++ Runtime 2015-2022"
    sys32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    required = ["vcruntime140.dll", "msvcp140.dll"]

    missing = [d for d in required if not (sys32 / d).exists()]
    if not missing:
        # 获取版本号
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64"
            )
            ver, _ = winreg.QueryValueEx(key, "Version")
            winreg.CloseKey(key)
            return PreflightItem(name, True, ver, "", [], "")
        except (FileNotFoundError, OSError):
            return PreflightItem(name, True, "Installed", "", [], "")

    return PreflightItem(
        name, False, f"Missing: {', '.join(missing)}",
        "https://aka.ms/vs/17/release/vc_redist.x64.exe",
        ["/install", "/passive", "/norestart"],
        "~24 MB",
    )


def check_git() -> PreflightItem:
    """检测 Git（只检测不安装）"""
    name = "Git"
    # 检测系统 Git
    try:
        result = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if result.returncode == 0:
            ver = result.stdout.strip().replace("git version ", "")
            return PreflightItem(name, True, ver, "", [], "")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 检测 MinGit（不依赖 backend 模块，直接检查常见路径）
    try:
        mingit_dir = get_mingit_dir()
        mingit_exe = mingit_dir / "cmd" / "git.exe"
        if mingit_exe.exists():
            return PreflightItem(name, True, "MinGit", "", [], "")
    except Exception:
        pass

    return PreflightItem(name, False, "Not installed", "", [], "")


# ============================================================
#  预检主入口
# ============================================================

def run_preflight() -> None:
    """
    运行启动预检。
    
    全部通过时静默返回。有缺失项时弹出 tkinter GUI。
    
    FULL 模式下（runtime/ 目录存在），跳过已内置的依赖检测，
    只检测 Git（不在 runtime 包中）。
    """
    if sys.platform != "win32":
        return

    try:
        # FULL 模式：检测 runtime/ 中已内置的依赖
        is_full_mode = os.environ.get('COMFYUI_BOX_FULL_MODE') == '1'
        runtime_dir = os.environ.get('COMFYUI_BOX_RUNTIME_DIR')

        if is_full_mode and runtime_dir:
            runtime_path = Path(runtime_dir)
            skip_dotnet = (runtime_path / "dotnet8" / "shared").exists()
            skip_webview2 = (runtime_path / "webview2" / "msedge.dll").exists()
            skip_vcruntime = (runtime_path / "vcruntime" / "vcruntime140.dll").exists()
        else:
            skip_dotnet = False
            skip_webview2 = False
            skip_vcruntime = False

        items = []
        for check_func in [check_dotnet8, check_webview2, check_vcruntime, check_git]:
            try:
                if check_func == check_dotnet8 and skip_dotnet:
                    items.append(PreflightItem(".NET 8 Desktop Runtime", True, "FULL Runtime", "", [], ""))
                    continue
                if check_func == check_webview2 and skip_webview2:
                    items.append(PreflightItem("Edge WebView2 Runtime", True, "FULL Runtime", "", [], ""))
                    continue
                if check_func == check_vcruntime and skip_vcruntime:
                    items.append(PreflightItem("VC++ Runtime 2015-2022", True, "FULL Runtime", "", [], ""))
                    continue
                items.append(check_func())
            except Exception as e:
                print(f"[Comfyui-Box] Check failed: {check_func.__name__}: {e}")
                items.append(PreflightItem(check_func.__name__, False, f"Check error: {e}", "", [], ""))

        failed = [it for it in items if not it.passed]

        if not failed:
            return

        _show_preflight_gui(items)
    except Exception as e:
        print(f"[Comfyui-Box] Preflight failed: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
#  tkinter GUI
# ============================================================

def _enable_dpi_awareness():
    """让 tkinter 窗口在高 DPI 下清晰显示，但不影响进程级 DPI 设置"""
    try:
        # 只调用 tk 的 DPI 缩放，不设置进程级 DPI awareness
        # 进程级设置会影响后续 pywebview 窗口的圆角和缩放行为
        pass  # tkinter 在 root.tk.call('tk', 'scaling') 时自动处理
    except Exception:
        pass


def _get_dpi_scale() -> float:
    """获取当前 DPI 缩放比例"""
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0


def _show_preflight_gui(items: List[PreflightItem]) -> None:
    """显示预检 GUI 窗口"""
    _enable_dpi_awareness()

    try:
        import tkinter as tk
        from tkinter import ttk, font as tkfont
    except ImportError:
        # tkinter 不可用，打印到控制台
        print("[Comfyui-Box] Preflight check - missing dependencies:")
        for it in items:
            status = "OK" if it.passed else "MISSING"
            print(f"  [{status}] {it.name}: {it.version}")
        return

    scale = _get_dpi_scale()

    # 颜色
    BG = "#1e1e2e"
    BG_CARD = "#27273a"
    FG = "#e4e4e7"
    DIM = "#71717a"
    ACCENT = "#7c3aed"
    ACCENT_LIGHT = "#a78bfa"
    GREEN = "#22c55e"
    RED = "#ef4444"
    YELLOW = "#eab308"

    # 窗口 — 按 DPI 缩放窗口尺寸，确保内容不被裁切
    win_w, win_h = int(460 * scale), int(500 * scale)
    root = tk.Tk()
    root.title("Comfyui-Box - System Check")
    root.geometry(f"{win_w}x{win_h}")
    root.resizable(False, False)
    root.configure(bg=BG)

    # 居中
    root.update_idletasks()
    sx = (root.winfo_screenwidth() - win_w) // 2
    sy = (root.winfo_screenheight() - win_h) // 2
    root.geometry(f"{win_w}x{win_h}+{sx}+{sy}")

    # 字体 — 不手动缩放，tkinter DPI aware 模式下自动处理 point 值
    font_title = ("Segoe UI", 14, "bold")
    font_sub = ("Segoe UI", 9)
    font_item = ("Segoe UI", 10)
    font_item_dim = ("Segoe UI", 8)
    font_btn = ("Segoe UI", 10, "bold")

    # 标题
    tk.Label(root, text="Comfyui-Box", font=font_title,
             fg=ACCENT_LIGHT, bg=BG).pack(pady=(20, 2))
    tk.Label(root, text="System Requirements Check", font=font_sub,
             fg=DIM, bg=BG).pack(pady=(0, 15))

    # 依赖列表容器
    list_frame = tk.Frame(root, bg=BG)
    list_frame.pack(fill=tk.X, padx=30)

    # 状态标签引用（用于安装后更新）
    status_labels = {}
    version_labels = {}

    for it in items:
        row = tk.Frame(list_frame, bg=BG_CARD, padx=12, pady=8)
        row.pack(fill=tk.X, pady=3)

        # 状态图标
        icon = "✓" if it.passed else "✗"
        color = GREEN if it.passed else RED
        icon_label = tk.Label(row, text=icon, font=("Segoe UI", 12, "bold"),
                              fg=color, bg=BG_CARD, width=2)
        icon_label.pack(side=tk.LEFT)
        status_labels[it.name] = icon_label

        # 名称和版本
        info_frame = tk.Frame(row, bg=BG_CARD)
        info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        tk.Label(info_frame, text=it.name, font=font_item,
                 fg=FG, bg=BG_CARD, anchor="w").pack(anchor="w")

        ver_text = it.version
        ver_color = DIM if it.passed else RED
        if not it.passed and it.size_hint:
            ver_text += f"  ({it.size_hint})"
        ver_label = tk.Label(info_frame, text=ver_text, font=font_item_dim,
                             fg=ver_color, bg=BG_CARD, anchor="w")
        ver_label.pack(anchor="w")
        version_labels[it.name] = ver_label

    # 可安装的缺失项
    installable = [it for it in items if not it.passed and it.install_url]
    non_installable = [it for it in items if not it.passed and not it.install_url]

    # 进度区域（列表下方，按钮上方）
    progress_frame = tk.Frame(root, bg=BG)
    progress_frame.pack(fill=tk.X, padx=30, pady=(10, 0))

    style = ttk.Style()
    style.theme_use('default')
    style.configure("PF.Horizontal.TProgressbar",
                    troughcolor="#27273a", background=ACCENT,
                    darkcolor=ACCENT, lightcolor=ACCENT_LIGHT,
                    bordercolor=BG, thickness=12)

    progress_var = tk.DoubleVar(value=0)
    progress_bar = ttk.Progressbar(progress_frame, length=400, mode='determinate',
                                    variable=progress_var,
                                    style="PF.Horizontal.TProgressbar")

    progress_text_var = tk.StringVar(value="")
    progress_label = tk.Label(progress_frame, textvariable=progress_text_var,
                              font=font_item_dim, fg=DIM, bg=BG)
    # 初始隐藏，安装时显示

    # 底部区域
    bottom_frame = tk.Frame(root, bg=BG)
    bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=30, pady=15)

    # 状态文本
    bottom_status = tk.StringVar()
    if non_installable:
        names = ", ".join(it.name for it in non_installable)
        bottom_status.set(f"{names} will be configured after startup")
    elif installable:
        bottom_status.set(f"{len(installable)} component(s) need to be installed")
    else:
        bottom_status.set("All requirements met!")

    tk.Label(bottom_frame, textvariable=bottom_status, font=font_sub,
             fg=DIM, bg=BG).pack(pady=(0, 4))

    # 按钮 — 用 Frame 包裹确保高度不被压缩
    btn_text = tk.StringVar(value=f"Install All ({len(installable)})" if installable else "Continue")
    btn_wrapper = tk.Frame(bottom_frame, bg=BG, height=44)
    btn_wrapper.pack(fill=tk.X)
    btn_wrapper.pack_propagate(False)

    btn = tk.Button(
        btn_wrapper, textvariable=btn_text, font=font_btn,
        bg=ACCENT, fg="white", activebackground=ACCENT_LIGHT,
        activeforeground="white", relief=tk.FLAT, cursor="hand2",
        bd=0, highlightthickness=0,
    )
    btn.pack(fill=tk.BOTH, expand=True)

    if not installable:
        # 没有可安装项，按钮直接关闭
        btn.configure(command=root.destroy)
        root.after(3000, root.destroy)
        root.mainloop()
        return

    # ========== 安装逻辑 ==========
    installing = [False]

    def do_install_all():
        if installing[0]:
            return
        installing[0] = True
        btn.configure(state=tk.DISABLED)
        btn_text.set("Installing...")

        # 显示进度条
        progress_bar.pack(fill=tk.X, pady=(4, 2))
        progress_label.pack(pady=(0, 4))

        def update_ui(func):
            """在主线程中安全更新 UI"""
            root.after(0, func)

        def worker():
            import urllib.request
            import ssl

            for idx, it in enumerate(installable):
                update_ui(lambda i=idx, n=it.name: (
                    bottom_status.set(f"[{i+1}/{len(installable)}] Downloading {n}..."),
                    status_labels[n].configure(text="⟳", fg=YELLOW),
                    progress_var.set(0),
                    progress_text_var.set("Connecting..."),
                ))

                installer_dir = Path(tempfile.gettempdir()) / "Comfyui-Box"
                installer_dir.mkdir(parents=True, exist_ok=True)
                fname = it.install_url.split("/")[-1]
                if "?" in fname or len(fname) < 5:
                    fname = f"installer_{idx}.exe"
                installer_path = installer_dir / fname

                try:
                    # 下载（带进度）
                    ctx = ssl.create_default_context()
                    req = urllib.request.Request(it.install_url, headers={"User-Agent": "Comfyui-Box/1.0"})
                    try:
                        resp = urllib.request.urlopen(req, context=ctx, timeout=300)
                    except ssl.SSLError:
                        ctx = ssl._create_unverified_context()
                        resp = urllib.request.urlopen(req, context=ctx, timeout=300)

                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0

                    with open(installer_path, "wb") as f:
                        while True:
                            chunk = resp.read(256 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                pct = downloaded * 100 / total
                                mb = downloaded / (1024 * 1024)
                                total_mb = total / (1024 * 1024)
                                update_ui(lambda p=pct, m=mb, t=total_mb: (
                                    progress_var.set(p),
                                    progress_text_var.set(f"{m:.1f} / {t:.1f} MB ({p:.0f}%)"),
                                ))
                    resp.close()

                    # 验证下载完整性
                    dl_size = installer_path.stat().st_size if installer_path.exists() else 0

                    # .NET 8 Runtime 应该 > 50MB，WebView2 bootstrapper > 1MB，VC++ > 20MB
                    min_sizes = {
                        ".NET 8 Desktop Runtime": 50 * 1024 * 1024,
                        "VC++ Runtime 2015-2022": 20 * 1024 * 1024,
                        "Edge WebView2 Runtime": 1 * 1024 * 1024,
                    }
                    min_size = min_sizes.get(it.name, 0)
                    if dl_size < min_size:
                        # 重试一次
                        if installer_path.exists():
                            installer_path.unlink()
                        update_ui(lambda n=it.name: progress_text_var.set(f"Download incomplete, retrying..."))
                        import time
                        time.sleep(2)

                        try:
                            ctx2 = ssl.create_default_context()
                            req2 = urllib.request.Request(it.install_url, headers={"User-Agent": "Comfyui-Box/1.0"})
                            try:
                                resp2 = urllib.request.urlopen(req2, context=ctx2, timeout=300)
                            except ssl.SSLError:
                                ctx2 = ssl._create_unverified_context()
                                resp2 = urllib.request.urlopen(req2, context=ctx2, timeout=300)

                            total2 = int(resp2.headers.get("Content-Length", 0))
                            downloaded2 = 0
                            with open(installer_path, "wb") as f2:
                                while True:
                                    chunk2 = resp2.read(256 * 1024)
                                    if not chunk2:
                                        break
                                    f2.write(chunk2)
                                    downloaded2 += len(chunk2)
                                    if total2 > 0:
                                        pct2 = downloaded2 * 100 / total2
                                        mb2 = downloaded2 / (1024 * 1024)
                                        tmb2 = total2 / (1024 * 1024)
                                        update_ui(lambda p=pct2, m=mb2, t=tmb2: (
                                            progress_var.set(p),
                                            progress_text_var.set(f"Retry: {m:.1f} / {t:.1f} MB ({p:.0f}%)"),
                                        ))
                            resp2.close()
                            dl_size = installer_path.stat().st_size
                        except Exception as e2:
                            print(f"[Comfyui-Box] Download retry failed: {e2}")

                    # 安装（可能需要管理员权限）
                    update_ui(lambda n=it.name, i=idx: (
                        bottom_status.set(f"[{i+1}/{len(installable)}] Installing {n}..."),
                        progress_var.set(100),
                        progress_text_var.set("Installing..."),
                    ))

                    # 第一次尝试：正常安装
                    proc = subprocess.Popen(
                        [str(installer_path)] + it.install_args,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=_get_creation_flags(),
                    )

                    update_ui(lambda: progress_text_var.set("Waiting for installer to finish..."))

                    try:
                        stdout, stderr = proc.communicate(timeout=300)
                        returncode = proc.returncode
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        returncode = -1

                    # 检查是否真的安装成功了（不信任返回码）
                    import time
                    time.sleep(2)
                    verify_func = {
                        ".NET 8 Desktop Runtime": check_dotnet8,
                        "Edge WebView2 Runtime": check_webview2,
                        "VC++ Runtime 2015-2022": check_vcruntime,
                    }.get(it.name)

                    actually_installed = False
                    if verify_func:
                        verify_result = verify_func()
                        actually_installed = verify_result.passed

                    # 如果返回码 0 但实际没装上（损坏安装的情况），尝试修复再重装
                    if not actually_installed and returncode == 0 and it.name == ".NET 8 Desktop Runtime":
                        print("[Comfyui-Box] Install not detected, attempting repair...")
                        update_ui(lambda: progress_text_var.set("Repairing existing installation..."))

                        # 先修复
                        proc2 = subprocess.Popen(
                            [str(installer_path), "/repair", "/passive", "/norestart"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=_get_creation_flags(),
                        )
                        try:
                            proc2.communicate(timeout=300)
                        except subprocess.TimeoutExpired:
                            proc2.kill()
                        time.sleep(2)
                        verify_result = verify_func()
                        actually_installed = verify_result.passed

                        # 修复也没用，卸载再重装
                        if not actually_installed:
                            print("[Comfyui-Box] Repair failed, attempting reinstall...")
                            update_ui(lambda: progress_text_var.set("Uninstalling broken installation..."))

                            proc3 = subprocess.Popen(
                                [str(installer_path), "/uninstall", "/passive", "/norestart"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=_get_creation_flags(),
                            )
                            try:
                                proc3.communicate(timeout=300)
                            except subprocess.TimeoutExpired:
                                proc3.kill()
                            time.sleep(3)
                            update_ui(lambda: progress_text_var.set("Reinstalling..."))

                            proc4 = subprocess.Popen(
                                [str(installer_path)] + it.install_args,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=_get_creation_flags(),
                            )
                            try:
                                proc4.communicate(timeout=300)
                            except subprocess.TimeoutExpired:
                                proc4.kill()
                            time.sleep(2)
                            verify_result = verify_func()
                            actually_installed = verify_result.passed

                    if actually_installed:
                        update_ui(lambda n=it.name: (
                            status_labels[n].configure(text="✓", fg=GREEN),
                            version_labels[n].configure(text="Installed", fg=DIM),
                        ))
                    elif returncode in (0, 1641, 3010, 1638):
                        # 返回码说成功但检测不到——标记为警告
                        update_ui(lambda n=it.name: (
                            status_labels[n].configure(text="!", fg=YELLOW),
                            version_labels[n].configure(text="May need restart", fg=YELLOW),
                        ))
                    else:
                        update_ui(lambda n=it.name, rc=returncode: (
                            status_labels[n].configure(text="!", fg=YELLOW),
                            version_labels[n].configure(text=f"Code {rc}", fg=YELLOW),
                        ))

                except Exception as e:
                    err_msg = str(e)[:40]
                    update_ui(lambda n=it.name, msg=err_msg: (
                        status_labels[n].configure(text="✗", fg=RED),
                        version_labels[n].configure(text=msg, fg=RED),
                    ))
                finally:
                    # 延迟清理安装包（安装进程可能还在用）
                    def _delayed_cleanup(p=installer_path):
                        import time
                        time.sleep(10)
                        if p.exists():
                            try:
                                p.unlink()
                            except Exception:
                                pass
                    threading.Thread(target=_delayed_cleanup, daemon=True).start()

            # 安装完成，重新检测（带重试，安装后文件系统可能有延迟）
            update_ui(lambda: (
                bottom_status.set("Verifying installation..."),
                progress_text_var.set(""),
            ))
            import time

            all_passed = False
            new_items = None
            for retry in range(5):
                time.sleep(2)
                new_items = [check_dotnet8(), check_webview2(), check_vcruntime(), check_git()]
                all_passed = all(it.passed for it in new_items)
                if all_passed:
                    break
                # 还有失败项，再等一下重试
                update_ui(lambda r=retry: progress_text_var.set(f"Waiting for installation to complete... ({r+1}/5)"))

            def finish_ui():
                for it in new_items:
                    if it.name in status_labels:
                        icon = "✓" if it.passed else "✗"
                        color = GREEN if it.passed else RED
                        status_labels[it.name].configure(text=icon, fg=color)
                        ver_color = DIM if it.passed else RED
                        version_labels[it.name].configure(text=it.version, fg=ver_color)

                progress_bar.pack_forget()
                progress_label.pack_forget()

                if all_passed:
                    bottom_status.set("All requirements met! Starting Comfyui-Box...")
                    btn_text.set("Continue")
                    btn.configure(state=tk.NORMAL, command=root.destroy)
                    root.after(2000, root.destroy)
                else:
                    still_missing = [it for it in new_items if not it.passed]
                    names = ", ".join(it.name for it in still_missing)
                    bottom_status.set(f"Still missing: {names}")
                    btn_text.set("Close")
                    btn.configure(state=tk.NORMAL, command=root.destroy)

            update_ui(finish_ui)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    btn.configure(command=do_install_all)

    # 运行 GUI
    try:
        root.mainloop()
    except Exception:
        pass
