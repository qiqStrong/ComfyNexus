@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo          Comfyui-Box 系统环境诊断工具
echo ============================================================
echo.

set ISSUE_COUNT=0
set WARNING_COUNT=0
set WEBVIEW2_FOUND=0

echo [1] 系统信息
echo ------------------------------------------------------------
ver
echo 系统架构: %PROCESSOR_ARCHITECTURE%
echo.

echo [2] WebView2 运行时检查 [关键]
echo ------------------------------------------------------------
reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] 系统注册表中找到 WebView2
    set WEBVIEW2_FOUND=1
)

reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] 用户注册表中找到 WebView2
    set WEBVIEW2_FOUND=1
)

if exist "%ProgramFiles(x86)%\Microsoft\EdgeWebView\Application\msedge.dll" (
    echo [OK] Program Files 中找到 WebView2
    set WEBVIEW2_FOUND=1
)

if exist "%LOCALAPPDATA%\Microsoft\EdgeWebView\Application\msedge.dll" (
    echo [OK] LocalAppData 中找到 WebView2
    set WEBVIEW2_FOUND=1
)

if %WEBVIEW2_FOUND% equ 0 (
    echo [错误] 未找到 WebView2 运行时！
    echo 这很可能是导致空白窗口的原因！
    set /a ISSUE_COUNT=ISSUE_COUNT+1
)
echo.

echo [3] 核心 DLL 检查
echo ------------------------------------------------------------
if exist "%SystemRoot%\System32\user32.dll" (echo [OK] user32.dll 存在) else (echo [错误] user32.dll 缺失 & set /a ISSUE_COUNT=ISSUE_COUNT+1)
if exist "%SystemRoot%\System32\kernel32.dll" (echo [OK] kernel32.dll 存在) else (echo [错误] kernel32.dll 缺失 & set /a ISSUE_COUNT=ISSUE_COUNT+1)
if exist "%SystemRoot%\System32\gdi32.dll" (echo [OK] gdi32.dll 存在) else (echo [错误] gdi32.dll 缺失 & set /a ISSUE_COUNT=ISSUE_COUNT+1)
if exist "%SystemRoot%\System32\shcore.dll" (echo [OK] shcore.dll 存在) else (echo [错误] shcore.dll 缺失 & set /a ISSUE_COUNT=ISSUE_COUNT+1)
if exist "%SystemRoot%\System32\ole32.dll" (echo [OK] ole32.dll 存在) else (echo [警告] ole32.dll 缺失 & set /a WARNING_COUNT=WARNING_COUNT+1)
echo.

echo [4] WMI 服务检查
echo ------------------------------------------------------------
sc query Winmgmt 2>nul | find "RUNNING" >nul
if %errorlevel% equ 0 (
    echo [OK] WMI 服务正在运行
) else (
    echo [警告] WMI 服务未运行，CPU 温度监控可能失效
    set /a WARNING_COUNT=WARNING_COUNT+1
)
echo.

echo [5] 显卡检查
echo ------------------------------------------------------------
wmic path win32_VideoController get name 2>nul
if %errorlevel% neq 0 (
    echo [警告] 无法获取显卡信息
    set /a WARNING_COUNT=WARNING_COUNT+1
)
echo.

echo [6] Visual C++ 运行时检查
echo ------------------------------------------------------------
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v Installed 2>nul | find "0x1" >nul
if %errorlevel% equ 0 (
    echo [OK] VC++ x64 运行时已安装
) else (
    echo [警告] VC++ x64 运行时可能未安装
    set /a WARNING_COUNT=WARNING_COUNT+1
)
echo.

echo ============================================================
echo                    诊断结果汇总
echo ============================================================
echo.
if %WEBVIEW2_FOUND% equ 0 (
    echo *** 严重问题: WebView2 运行时未安装！***
    echo.
    echo 这很可能是导致空白窗口的原因。
    echo.
    echo 请下载并安装 WebView2 运行时:
    echo https://go.microsoft.com/fwlink/p/?LinkId=2124703
    echo.
) else (
    echo WebView2 运行时: 正常
)
echo.
echo 严重问题数: %ISSUE_COUNT%
echo 警告数: %WARNING_COUNT%
echo.
echo ============================================================
echo.
pause
