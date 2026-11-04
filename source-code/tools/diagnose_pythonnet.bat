@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ============================================================
echo    Comfyui-Box Diagnostic Tool for Packaged Environment
echo ============================================================
echo.

:: Get script directory (assume placed next to exe)
set "APP_DIR=%~dp0"
set "INTERNAL_DIR=%APP_DIR%_internal"

echo [INFO] App Directory: %APP_DIR%
echo [INFO] Internal Directory: %INTERNAL_DIR%
echo.

:: 1. Check _internal directory
echo [1/6] Checking packaged directory structure...
if exist "%INTERNAL_DIR%" (
    echo [OK] _internal directory exists
) else (
    echo [ERROR] _internal directory not found
    echo        Please place this script next to Comfyui-Box.exe
    goto :end
)
echo.

:: 2. Check pythonnet files
echo [2/6] Checking pythonnet files...
set "PYTHONNET_DIR=%INTERNAL_DIR%\pythonnet"
if exist "%PYTHONNET_DIR%" (
    echo [OK] pythonnet directory exists
    
    set "RUNTIME_DLL=%PYTHONNET_DIR%\runtime\Python.Runtime.dll"
    if exist "!RUNTIME_DLL!" (
        for %%F in ("!RUNTIME_DLL!") do set "DLL_SIZE=%%~zF"
        set /a "DLL_SIZE_MB=!DLL_SIZE! / 1048576"
        echo [OK] Python.Runtime.dll exists ^(!DLL_SIZE_MB! MB^)
    ) else (
        echo [ERROR] Python.Runtime.dll not found
        echo        Path: !RUNTIME_DLL!
    )
) else (
    echo [WARN] pythonnet directory not found
)
echo.

:: 3. Check .NET Framework version
echo [3/6] Checking .NET Framework version...
reg query "HKLM\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" /v Release >nul 2>&1
if !errorlevel! equ 0 (
    for /f "tokens=3" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" /v Release 2^>nul') do (
        set DOTNET_RELEASE=%%a
    )
    if defined DOTNET_RELEASE (
        if !DOTNET_RELEASE! geq 528040 (
            echo [OK] .NET Framework 4.8+ ^(Release: !DOTNET_RELEASE!^)
        ) else if !DOTNET_RELEASE! geq 461808 (
            echo [OK] .NET Framework 4.7.2 ^(Release: !DOTNET_RELEASE!^)
        ) else if !DOTNET_RELEASE! geq 394802 (
            echo [WARN] .NET Framework 4.6.2 ^(Release: !DOTNET_RELEASE!^)
        ) else (
            echo [ERROR] .NET Framework version too low ^(Release: !DOTNET_RELEASE!^)
        )
    )
) else (
    echo [WARN] Cannot detect .NET Framework version
)
echo.

:: 4. Check WebView2 Runtime
echo [4/6] Checking WebView2 Runtime...
set WEBVIEW2_FOUND=0
reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1
if !errorlevel! equ 0 (
    for /f "tokens=3" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv 2^>nul') do (
        echo [OK] WebView2 Runtime installed: %%a
        set WEBVIEW2_FOUND=1
    )
)
if !WEBVIEW2_FOUND! equ 0 (
    reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=3" %%a in ('reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv 2^>nul') do (
            echo [OK] WebView2 Runtime installed ^(user^): %%a
            set WEBVIEW2_FOUND=1
        )
    )
)
if !WEBVIEW2_FOUND! equ 0 (
    echo [WARN] WebView2 Runtime not installed
    echo        Download: https://developer.microsoft.com/en-us/microsoft-edge/webview2/
)
echo.

:: 5. Check Visual C++ Redistributable
echo [5/6] Checking Visual C++ Redistributable...
set VCPP_FOUND=0
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v Installed >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK] VC++ Redistributable x64 installed
    set VCPP_FOUND=1
)
if !VCPP_FOUND! equ 0 (
    reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v Installed >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] VC++ Redistributable x64 installed
        set VCPP_FOUND=1
    )
)
if !VCPP_FOUND! equ 0 (
    echo [WARN] VC++ Redistributable x64 not detected
    echo        Download: https://aka.ms/vs/17/release/vc_redist.x64.exe
)
echo.

:: 6. Check admin privileges
echo [6/6] Checking admin privileges...
net session >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK] Running with admin privileges
) else (
    echo [INFO] Not running as admin - Hardware monitoring requires admin
)
echo.

echo ============================================================
echo    Diagnostic Complete
echo ============================================================
echo.
echo If Comfyui-Box fails to start, try:
echo   1. Install WebView2 Runtime ^(recommended^)
echo   2. Install Visual C++ Redistributable
echo   3. Run Comfyui-Box.exe as Administrator
echo   4. Check antivirus software
echo.

:end
pause
