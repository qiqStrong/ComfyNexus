"""
WebView2 启动诊断窗口

当检测到 WebView2 控件未正常初始化时，使用 tkinter 弹出诊断窗口。
tkinter 不依赖 .NET / WebView2，在任何 Windows 系统上都能运行。
"""

import os
import sys
from pathlib import Path


def show_webview2_diagnostic(error_info: str = "") -> str:
    """
    弹出 WebView2 诊断窗口，返回用户选择的操作。

    返回值:
        "safe_mode" - 以安全模式重试（禁用 GPU 加速）
        "exit" - 退出应用
    """
    try:
        import tkinter as tk
    except ImportError:
        return "exit"

    result = {"action": "exit"}

    root = tk.Tk()
    root.title("Comfyui-Box - 启动诊断")
    root.geometry("520x420")
    root.resizable(False, False)
    root.configure(bg="#1e1e2e")

    root.update_idletasks()
    x = (root.winfo_screenwidth() - 520) // 2
    y = (root.winfo_screenheight() - 420) // 2
    root.geometry(f"520x420+{x}+{y}")

    BG = "#1e1e2e"
    FG = "#e4e4e7"
    ACCENT = "#7c3aed"
    ACCENT_LIGHT = "#a78bfa"
    DIM = "#71717a"
    ERROR_COLOR = "#ef4444"
    SUCCESS = "#22c55e"

    tk.Label(root, text="Comfyui-Box", font=("Segoe UI", 18, "bold"),
             fg=ACCENT_LIGHT, bg=BG).pack(pady=(20, 2))

    tk.Label(root, text="WebView2 初始化失败", font=("Segoe UI", 12),
             fg=ERROR_COLOR, bg=BG).pack(pady=(0, 12))

    diag_frame = tk.Frame(root, bg="#27273a", padx=16, pady=12)
    diag_frame.pack(fill=tk.X, padx=24, pady=(0, 8))

    runtime_dir = os.environ.get('COMFYUI_BOX_RUNTIME_DIR', '')
    checks = [
        ("WebView2 Fixed Version", bool(os.environ.get('WEBVIEW2_BROWSER_EXECUTABLE_FOLDER'))),
        (".NET 8 Runtime", bool(os.environ.get('COMFYUI_BOX_FULL_MODE'))),
        ("VC++ Runtime", runtime_dir and (Path(runtime_dir) / "vcruntime").exists()),
    ]

    for name, ok in checks:
        status = "OK" if ok else "MISSING"
        color = SUCCESS if ok else ERROR_COLOR
        row = tk.Frame(diag_frame, bg="#27273a")
        row.pack(fill=tk.X, pady=1)
        tk.Label(row, text=name, font=("Segoe UI", 9), fg=DIM, bg="#27273a",
                 anchor="w").pack(side=tk.LEFT)
        tk.Label(row, text=status, font=("Segoe UI", 9, "bold"), fg=color, bg="#27273a",
                 anchor="e").pack(side=tk.RIGHT)

    if error_info:
        tk.Label(root, text=f"错误: {error_info[:80]}", font=("Segoe UI", 9),
                 fg=DIM, bg=BG, wraplength=470).pack(pady=(4, 8))

    tk.Label(root, text="可能的原因:", font=("Segoe UI", 10, "bold"),
             fg=FG, bg=BG).pack(pady=(4, 2))

    causes = [
        "• GPU 驱动不兼容或虚拟机环境",
        "• 安全软件阻止了浏览器组件",
        "• 运行时文件不完整",
    ]
    for cause in causes:
        tk.Label(root, text=cause, font=("Segoe UI", 9), fg=DIM, bg=BG,
                 anchor="w").pack(fill=tk.X, padx=40)

    btn_frame = tk.Frame(root, bg=BG)
    btn_frame.pack(pady=(16, 12))

    def on_safe_mode():
        result["action"] = "safe_mode"
        root.destroy()

    def on_exit():
        result["action"] = "exit"
        root.destroy()

    safe_btn = tk.Button(
        btn_frame, text="安全模式重试", font=("Segoe UI", 10),
        fg="white", bg=ACCENT, activebackground=ACCENT_LIGHT,
        relief=tk.FLAT, padx=20, pady=6, cursor="hand2",
        command=on_safe_mode
    )
    safe_btn.pack(side=tk.LEFT, padx=8)

    exit_btn = tk.Button(
        btn_frame, text="退出应用", font=("Segoe UI", 10),
        fg=FG, bg="#3f3f50", activebackground="#4f4f60",
        relief=tk.FLAT, padx=20, pady=6, cursor="hand2",
        command=on_exit
    )
    exit_btn.pack(side=tk.LEFT, padx=8)

    tk.Label(root, text="安全模式将禁用 GPU 加速，界面可能略有卡顿",
             font=("Segoe UI", 8), fg=DIM, bg=BG).pack(side=tk.BOTTOM, pady=(0, 8))

    try:
        root.mainloop()
    except Exception:
        pass

    return result["action"]


def get_safe_mode_marker_path() -> Path:
    """获取安全模式标记文件路径"""
    local_app_data = os.environ.get('LOCALAPPDATA')
    if local_app_data:
        return Path(local_app_data) / 'Comfyui-Box' / '.safe_mode'
    return Path.home() / '.comfyui-box_safe_mode'


def is_safe_mode() -> bool:
    """检查是否应该使用安全模式"""
    return get_safe_mode_marker_path().exists()


def set_safe_mode(enabled: bool) -> None:
    """设置或清除安全模式标记"""
    marker = get_safe_mode_marker_path()
    if enabled:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    else:
        if marker.exists():
            try:
                marker.unlink()
            except Exception:
                pass
