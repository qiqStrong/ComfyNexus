@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>nul
title Comfyui-Box Deep Dependency Checker v2.0

:: ============================================================
::  Comfyui-Box Deep Dependency Checker v2.0
::  Checks ALL runtime dependencies at DLL granularity level
::  No PowerShell required - pure CMD script
:: ============================================================

set "PASS=0"
set "FAIL=0"
set "WARN=0"
set "LOGFILE=%~dp0deep_check_result.log"

:: Clear log file
echo Comfyui-Box Deep Dependency Check Report > "%LOGFILE%"
echo Generated: %date% %time% >> "%LOGFILE%"
echo ============================================================ >> "%LOGFILE%"
echo. >> "%LOGFILE%"

echo.
echo ============================================================
echo  Comfyui-Box Deep Dependency Checker v2.0
echo ============================================================
echo  Time: %date% %time%
echo  Log:  %LOGFILE%
echo ============================================================
echo.

:: ============================================================
::  SECTION 1: System Information
:: ============================================================
echo [Section 1/8] System Information
echo ============================================================
echo.

for /f "tokens=*" %%i in ('ver') do set "WINVER_FULL=%%i"
echo   OS: %WINVER_FULL%
echo   Architecture: %PROCESSOR_ARCHITECTURE%

for /f "tokens=6 delims=[]. " %%i in ('ver') do set "BUILD=%%i"
echo   Build: %BUILD%

echo. >> "%LOGFILE%"
echo [System Information] >> "%LOGFILE%"
echo   OS: %WINVER_FULL% >> "%LOGFILE%"
echo   Architecture: %PROCESSOR_ARCHITECTURE% >> "%LOGFILE%"
echo   Build: %BUILD% >> "%LOGFILE%"

if !BUILD! GEQ 17134 (
    call :pass "Windows Version" "Build !BUILD! - OK (Win10 1803+)"
) else (
    call :fail "Windows Version" "Build !BUILD! too old. Need Win10 1803+ (Build 17134+)"
)
echo.

:: ============================================================
::  SECTION 2: Core System DLLs
:: ============================================================
echo [Section 2/8] Core System DLLs
echo ============================================================
echo.

set "SYS32=%SystemRoot%\System32"

call :check_dll "%SYS32%\kernel32.dll"  "kernel32.dll"  "REQUIRED" "Process management, file ops, mutex"
call :check_dll "%SYS32%\user32.dll"    "user32.dll"    "REQUIRED" "Window management, input"
call :check_dll "%SYS32%\shell32.dll"   "shell32.dll"   "REQUIRED" "Shell operations, admin check"
call :check_dll "%SYS32%\shcore.dll"    "shcore.dll"    "REQUIRED" "DPI awareness"
call :check_dll "%SYS32%\gdi32.dll"     "gdi32.dll"     "REQUIRED" "Graphics device interface"
call :check_dll "%SYS32%\advapi32.dll"  "advapi32.dll"  "REQUIRED" "Registry, security, services"
call :check_dll "%SYS32%\ole32.dll"     "ole32.dll"     "REQUIRED" "COM infrastructure"
call :check_dll "%SYS32%\oleaut32.dll"  "oleaut32.dll"  "REQUIRED" "COM automation"
call :check_dll "%SYS32%\dwmapi.dll"    "dwmapi.dll"    "OPTIONAL" "Window rounded corners (Win11)"
call :check_dll "%SYS32%\ws2_32.dll"    "ws2_32.dll"    "REQUIRED" "Winsock - TCP/IP networking"
call :check_dll "%SYS32%\crypt32.dll"   "crypt32.dll"   "REQUIRED" "SSL/TLS certificate handling"
call :check_dll "%SYS32%\secur32.dll"   "secur32.dll"   "REQUIRED" "Security authentication"
call :check_dll "%SYS32%\winhttp.dll"   "winhttp.dll"   "REQUIRED" "HTTP client (WebView2 uses)"
call :check_dll "%SYS32%\wininet.dll"   "wininet.dll"   "REQUIRED" "Internet functions"
echo.

:: ============================================================
::  SECTION 3: VC++ Runtime (CRITICAL - often missing!)
:: ============================================================
echo [Section 3/8] Visual C++ Runtime
echo ============================================================
echo.
echo   This is the #1 cause of crashes on stripped Windows installs.
echo.

call :check_dll "%SYS32%\vcruntime140.dll"      "vcruntime140.dll"      "REQUIRED" "VC++ 2015-2022 Runtime (core)"
call :check_dll "%SYS32%\vcruntime140_1.dll"     "vcruntime140_1.dll"    "REQUIRED" "VC++ 2015-2022 Runtime (ext)"
call :check_dll "%SYS32%\msvcp140.dll"           "msvcp140.dll"          "REQUIRED" "VC++ 2015-2022 Standard Library"
call :check_dll "%SYS32%\msvcp140_1.dll"         "msvcp140_1.dll"        "OPTIONAL" "VC++ 2015-2022 Standard Library (ext)"
call :check_dll "%SYS32%\msvcp140_2.dll"         "msvcp140_2.dll"        "OPTIONAL" "VC++ 2015-2022 Standard Library (ext2)"
call :check_dll "%SYS32%\concrt140.dll"          "concrt140.dll"         "OPTIONAL" "VC++ Concurrency Runtime"
call :check_dll "%SYS32%\vccorlib140.dll"        "vccorlib140.dll"       "OPTIONAL" "VC++ WinRT core library"
call :check_dll "%SYS32%\vcomp140.dll"           "vcomp140.dll"          "OPTIONAL" "VC++ OpenMP Runtime"

echo.
echo   Checking VC++ Redistributable installation via registry...
set "VCREDIST_FOUND=0"
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64" /v Version >nul 2>nul
if !errorlevel! equ 0 (
    for /f "tokens=3" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64" /v Version 2^>nul ^| findstr Version') do (
        call :pass "VC++ Redist x64 [registry]" "Version %%a"
        set "VCREDIST_FOUND=1"
    )
)
if !VCREDIST_FOUND! equ 0 (
    reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\X64" /v Version >nul 2>nul
    if !errorlevel! equ 0 (
        for /f "tokens=3" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\X64" /v Version 2^>nul ^| findstr Version') do (
            call :pass "VC++ Redist x64 [registry]" "Version %%a"
            set "VCREDIST_FOUND=1"
        )
    )
)
if !VCREDIST_FOUND! equ 0 (
    call :fail "VC++ Redist x64 [registry]" "NOT FOUND - Download https://aka.ms/vs/17/release/vc_redist.x64.exe"
)
echo.

:: ============================================================
::  SECTION 4: Universal CRT (UCRT)
:: ============================================================
echo [Section 4/8] Universal C Runtime - UCRT
echo ============================================================
echo.
echo   UCRT is built into Win10+. On Win10+ the api-ms-win-crt-* DLLs
echo   may live in System32\downlevel\ instead of System32\ directly.
echo   Both locations are valid - the OS API Set resolves them at runtime.
echo.

call :check_dll "%SYS32%\ucrtbase.dll" "ucrtbase.dll" "REQUIRED" "Universal CRT base"

:: api-ms-win-crt forwarding DLLs - check both System32 and downlevel
call :check_ucrt "api-ms-win-crt-runtime-l1-1-0.dll"     "CRT runtime forwarder"
call :check_ucrt "api-ms-win-crt-heap-l1-1-0.dll"        "CRT heap forwarder"
call :check_ucrt "api-ms-win-crt-string-l1-1-0.dll"      "CRT string forwarder"
call :check_ucrt "api-ms-win-crt-stdio-l1-1-0.dll"       "CRT stdio forwarder"
call :check_ucrt "api-ms-win-crt-math-l1-1-0.dll"        "CRT math forwarder"
call :check_ucrt "api-ms-win-crt-locale-l1-1-0.dll"      "CRT locale forwarder"
call :check_ucrt "api-ms-win-crt-time-l1-1-0.dll"        "CRT time forwarder"
call :check_ucrt "api-ms-win-crt-convert-l1-1-0.dll"     "CRT convert forwarder"
call :check_ucrt "api-ms-win-crt-environment-l1-1-0.dll"  "CRT environment forwarder"
call :check_ucrt "api-ms-win-crt-process-l1-1-0.dll"     "CRT process forwarder"
call :check_ucrt "api-ms-win-crt-filesystem-l1-1-0.dll"  "CRT filesystem forwarder"
call :check_ucrt "api-ms-win-crt-utility-l1-1-0.dll"     "CRT utility forwarder"
call :check_ucrt "api-ms-win-crt-multibyte-l1-1-0.dll"   "CRT multibyte forwarder"
call :check_ucrt "api-ms-win-crt-conio-l1-1-0.dll"       "CRT console IO forwarder"
echo.

:: ============================================================
::  SECTION 5: .NET Framework (pythonnet dependency)
:: ============================================================
echo [Section 5/8] .NET Framework
echo ============================================================
echo.
echo   pywebview uses pythonnet which requires .NET Framework 4.6.2+
echo.

set "DOTNET_FOUND=0"
set "DOTNET_RELEASE=0"
reg query "HKLM\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" /v Release >nul 2>nul
if !errorlevel! equ 0 (
    for /f "tokens=3" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" /v Release 2^>nul ^| findstr Release') do (
        set "DOTNET_RELEASE=%%a"
        set "DOTNET_FOUND=1"
    )
)

if !DOTNET_FOUND! equ 1 (
    if !DOTNET_RELEASE! GEQ 528040 (
        call :pass ".NET Framework 4.8+" "Release key !DOTNET_RELEASE!"
    ) else if !DOTNET_RELEASE! GEQ 394802 (
        call :pass ".NET Framework 4.6.2+" "Release key !DOTNET_RELEASE! - 4.8+ recommended"
    ) else (
        call :fail ".NET Framework" "Too old. Release key !DOTNET_RELEASE! - need 4.6.2+ key 394802+"
    )
) else (
    call :fail ".NET Framework" "NOT FOUND. Required by pythonnet/pywebview"
)

set "DOTNET_DIR=%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319"
if not exist "%DOTNET_DIR%" set "DOTNET_DIR=%SystemRoot%\Microsoft.NET\Framework\v4.0.30319"

if exist "%DOTNET_DIR%" (
    echo.
    echo   .NET Framework directory: %DOTNET_DIR%
    call :check_dll "%DOTNET_DIR%\clr.dll"                    "clr.dll"                    "REQUIRED" ".NET CLR engine"
    call :check_dll "%DOTNET_DIR%\clrjit.dll"                 "clrjit.dll"                 "REQUIRED" ".NET JIT compiler"
    call :check_dll "%DOTNET_DIR%\mscorlib.dll"               "mscorlib.dll"               "REQUIRED" ".NET core library"
    call :check_dll "%DOTNET_DIR%\System.dll"                 "System.dll"                 "REQUIRED" ".NET System assembly"
    call :check_dll "%DOTNET_DIR%\System.Windows.Forms.dll"   "System.Windows.Forms.dll"   "REQUIRED" "WinForms - pywebview host"
    call :check_dll "%DOTNET_DIR%\System.Drawing.dll"         "System.Drawing.dll"         "REQUIRED" "Drawing - pywebview UI"
    call :check_dll "%DOTNET_DIR%\System.Core.dll"            "System.Core.dll"            "REQUIRED" ".NET Core extensions"
    call :check_dll "%DOTNET_DIR%\System.Collections.dll"     "System.Collections.dll"     "OPTIONAL" ".NET Collections"
) else (
    call :fail ".NET Framework Directory" "NOT FOUND at expected path"
)
echo.

:: ============================================================
::  SECTION 6: WebView2 Runtime
:: ============================================================
echo [Section 6/8] Edge WebView2 Runtime
echo ============================================================
echo.

set "WV2_FOUND=0"
set "WV2_VERSION=unknown"

for %%K in (
    "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
) do (
    if !WV2_FOUND! equ 0 (
        reg query %%K /v pv >nul 2>nul
        if !errorlevel! equ 0 (
            for /f "tokens=3" %%a in ('reg query %%K /v pv 2^>nul ^| findstr pv') do (
                if not "%%a"=="" if not "%%a"=="0.0.0.0" (
                    set "WV2_VERSION=%%a"
                    set "WV2_FOUND=1"
                )
            )
        )
    )
)

if !WV2_FOUND! equ 0 (
    if exist "%ProgramFiles(x86)%\Microsoft\EdgeWebView\Application" (
        for /d %%d in ("%ProgramFiles(x86)%\Microsoft\EdgeWebView\Application\*") do (
            set "WV2_VERSION=%%~nxd"
            set "WV2_FOUND=1"
        )
    )
)

if !WV2_FOUND! equ 1 (
    call :pass "WebView2 Runtime" "Version !WV2_VERSION!"
) else (
    call :fail "WebView2 Runtime" "NOT FOUND - Download https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
)

:: Check WebView2Loader.dll in pywebview package
set "WV2_LOADER_FOUND=0"
set "PYWEBVIEW_LIB=%~dp0..\.venv\Lib\site-packages\webview\lib"
if exist "%PYWEBVIEW_LIB%" (
    echo.
    echo   Checking pywebview bundled WebView2 SDK...
    if exist "%PYWEBVIEW_LIB%\Microsoft.Web.WebView2.Core.dll" (
        call :pass "WebView2.Core.dll [bundled]" "Found in pywebview package"
        set "WV2_LOADER_FOUND=1"
    ) else (
        call :warn "WebView2.Core.dll [bundled]" "Not found in pywebview package"
    )
    if exist "%PYWEBVIEW_LIB%\Microsoft.Web.WebView2.WinForms.dll" (
        call :pass "WebView2.WinForms.dll [bundled]" "Found in pywebview package"
    ) else (
        call :warn "WebView2.WinForms.dll [bundled]" "Not found in pywebview package"
    )
)
echo.

:: ============================================================
::  SECTION 7: Windows API Subsystems
:: ============================================================
echo [Section 7/8] Windows API Subsystems
echo ============================================================
echo.

call :check_dll "%SYS32%\combase.dll"    "combase.dll"    "REQUIRED" "COM base runtime"
call :check_dll "%SYS32%\rpcrt4.dll"     "rpcrt4.dll"     "REQUIRED" "RPC runtime"
call :check_dll "%SYS32%\mscoree.dll"    "mscoree.dll"    "REQUIRED" ".NET execution engine shim"
call :check_dll "%SYS32%\shlwapi.dll"    "shlwapi.dll"    "REQUIRED" "Shell lightweight utility"
call :check_dll "%SYS32%\urlmon.dll"     "urlmon.dll"     "REQUIRED" "URL moniker - WebView2 uses"
call :check_dll "%SYS32%\version.dll"    "version.dll"    "REQUIRED" "Version info API"
call :check_dll "%SYS32%\bcrypt.dll"     "bcrypt.dll"     "REQUIRED" "Crypto next-gen"
call :check_dll "%SYS32%\ncrypt.dll"     "ncrypt.dll"     "REQUIRED" "Key storage crypto"
call :check_dll "%SYS32%\ntdll.dll"      "ntdll.dll"      "REQUIRED" "NT layer DLL"
call :check_dll "%SYS32%\msvcrt.dll"     "msvcrt.dll"     "REQUIRED" "Legacy C runtime"
call :check_dll "%SYS32%\mswsock.dll"    "mswsock.dll"    "REQUIRED" "Winsock helper"
call :check_dll "%SYS32%\dnsapi.dll"     "dnsapi.dll"     "REQUIRED" "DNS client API"
call :check_dll "%SYS32%\iphlpapi.dll"   "iphlpapi.dll"   "REQUIRED" "IP helper - port detection"
echo.

:: ============================================================
::  SECTION 8: System Tools and Services
:: ============================================================
echo [Section 8/8] System Tools and Services
echo ============================================================
echo.

if exist "%SystemRoot%\System32\cmd.exe" (
    call :pass "cmd.exe" "Available"
) else (
    call :fail "cmd.exe" "MISSING"
)

if exist "%SystemRoot%\System32\reg.exe" (
    call :pass "reg.exe" "Available"
) else (
    call :fail "reg.exe" "MISSING"
)

if exist "%SystemRoot%\System32\sc.exe" (
    call :pass "sc.exe" "Available"
) else (
    call :warn "sc.exe" "MISSING - service control"
)

if exist "%SystemRoot%\System32\netsh.exe" (
    call :pass "netsh.exe" "Available"
) else (
    call :warn "netsh.exe" "MISSING - network config"
)

:: TCP port binding test using PowerShell (best-effort, skip if PS unavailable)
echo.
echo   Testing TCP port binding capability...
where powershell >nul 2>nul
if !errorlevel! equ 0 (
    powershell -NoProfile -Command "try{$l=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,0);$l.Start();$p=$l.LocalEndpoint.Port;$l.Stop();Write-Host '  TCP OK - test bound port' $p}catch{Write-Host '  TCP FAILED:' $_}" 2>nul
) else (
    echo   [INFO] PowerShell not available, skipping TCP test
)
echo.

:: ============================================================
::  SUMMARY
:: ============================================================
echo.
echo ============================================================
echo  SUMMARY
echo ============================================================
echo.

set /a "TOTAL=PASS+FAIL+WARN"
echo   Total checks:  !TOTAL!
echo   [PASS] Passed:            !PASS!
echo   [FAIL] Failed [Required]:  !FAIL!
echo   [WARN] Warning [Optional]: !WARN!
echo.

echo. >> "%LOGFILE%"
echo [Summary] >> "%LOGFILE%"
echo   Total: !TOTAL!, Pass: !PASS!, Fail: !FAIL!, Warn: !WARN! >> "%LOGFILE%"

if !FAIL! GTR 0 (
    echo ============================================================
    echo  REQUIRED DEPENDENCIES MISSING - Comfyui-Box may not start
    echo ============================================================
    echo.
    echo  Recommended fixes in order:
    echo.
    echo  1. Install VC++ Redistributable 2015-2022 x64:
    echo     https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo.
    echo  2. Install or enable .NET Framework 4.8:
    echo     https://dotnet.microsoft.com/en-us/download/dotnet-framework/net48
    echo     Or run as admin: DISM /Online /Enable-Feature /FeatureName:NetFx4 /All
    echo.
    echo  3. Install WebView2 Runtime:
    echo     https://developer.microsoft.com/en-us/microsoft-edge/webview2/
    echo.
    echo  4. If using a stripped or lite Windows, run system repair:
    echo     DISM /Online /Cleanup-Image /RestoreHealth
    echo     sfc /scannow
    echo.
    echo. >> "%LOGFILE%"
    echo [ACTION REQUIRED] See recommended fixes above >> "%LOGFILE%"
) else (
    echo ============================================================
    echo  ALL REQUIRED DEPENDENCIES FOUND
    echo ============================================================
    echo.
    if !WARN! GTR 0 (
        echo  Some optional components are missing - non-critical.
    ) else (
        echo  System is fully ready for Comfyui-Box.
    )
)

echo.
echo  Full log saved to: %LOGFILE%
echo.
echo ============================================================
echo  Press any key to exit...
echo ============================================================
pause >nul
exit /b !FAIL!

:: ============================================================
::  HELPER FUNCTIONS
:: ============================================================

:check_dll
:: %1 = full path, %2 = display name, %3 = REQUIRED/OPTIONAL, %4 = description
if exist "%~1" (
    for %%F in ("%~1") do set "FSIZE=%%~zF"
    call :pass "%~2" "%~4 [!FSIZE! bytes]"
) else (
    if "%~3"=="REQUIRED" (
        call :fail "%~2" "MISSING - %~4"
    ) else (
        call :warn "%~2" "MISSING - %~4"
    )
)
goto :eof

:check_ucrt
:: %1 = dll name, %2 = description
:: Check System32 first, then downlevel (Win10+ API Set location)
set "UCRT_DLL_FOUND=0"
if exist "%SYS32%\%~1" (
    for %%F in ("%SYS32%\%~1") do set "FSIZE=%%~zF"
    call :pass "%~1" "%~2 [!FSIZE! bytes]"
    set "UCRT_DLL_FOUND=1"
)
if !UCRT_DLL_FOUND! equ 0 (
    if exist "%SYS32%\downlevel\%~1" (
        for %%F in ("%SYS32%\downlevel\%~1") do set "FSIZE=%%~zF"
        call :pass "%~1" "%~2 [downlevel, !FSIZE! bytes]"
        set "UCRT_DLL_FOUND=1"
    )
)
if !UCRT_DLL_FOUND! equ 0 (
    call :fail "%~1" "MISSING - %~2"
)
goto :eof

:pass
set /a "PASS+=1"
echo   [PASS] %~1: %~2
echo   [PASS] %~1: %~2 >> "%LOGFILE%"
goto :eof

:fail
set /a "FAIL+=1"
echo   [FAIL] %~1: %~2
echo   [FAIL] %~1: %~2 >> "%LOGFILE%"
goto :eof

:warn
set /a "WARN+=1"
echo   [WARN] %~1: %~2
echo   [WARN] %~1: %~2 >> "%LOGFILE%"
goto :eof
