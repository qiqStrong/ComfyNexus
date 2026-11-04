#Requires -Version 5.1
# Comfyui-Box Diagnostic Script for Packaged Environment

$Host.UI.RawUI.WindowTitle = "Comfyui-Box Diagnostic Tool"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   Comfyui-Box Diagnostic Tool for Packaged Environment" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$internalDir = Join-Path $scriptDir "_internal"

Write-Host "[INFO] App Directory: $scriptDir" -ForegroundColor Gray
Write-Host "[INFO] Internal Directory: $internalDir" -ForegroundColor Gray
Write-Host ""

$issues = @()
$warnings = @()

# 1. Check _internal directory
Write-Host "[1/6] Checking packaged directory structure..." -ForegroundColor Yellow
if (Test-Path $internalDir) {
    Write-Host "  [OK] _internal directory exists" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] _internal directory not found" -ForegroundColor Red
    Write-Host "         Please place this script next to Comfyui-Box.exe" -ForegroundColor Red
    $issues += "_internal directory not found"
}
Write-Host ""

# 2. Check pythonnet files
Write-Host "[2/6] Checking pythonnet files..." -ForegroundColor Yellow
$pythonnetDir = Join-Path $internalDir "pythonnet"
if (Test-Path $pythonnetDir) {
    Write-Host "  [OK] pythonnet directory exists" -ForegroundColor Green
    
    $runtimeDll = Join-Path $pythonnetDir "runtime\Python.Runtime.dll"
    if (Test-Path $runtimeDll) {
        $dllInfo = Get-Item $runtimeDll
        $dllSizeMB = [math]::Round($dllInfo.Length / 1MB, 2)
        Write-Host "  [OK] Python.Runtime.dll exists ($dllSizeMB MB)" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] Python.Runtime.dll not found" -ForegroundColor Red
        Write-Host "         Path: $runtimeDll" -ForegroundColor Red
        $issues += "Python.Runtime.dll not found"
    }
} else {
    Write-Host "  [WARN] pythonnet directory not found" -ForegroundColor Yellow
    $warnings += "pythonnet directory not found"
}
Write-Host ""

# 3. Check .NET Framework version
Write-Host "[3/6] Checking .NET Framework version..." -ForegroundColor Yellow
try {
    $release = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" -ErrorAction Stop).Release
    if ($release -ge 528040) {
        Write-Host "  [OK] .NET Framework 4.8+ (Release: $release)" -ForegroundColor Green
    } elseif ($release -ge 461808) {
        Write-Host "  [OK] .NET Framework 4.7.2 (Release: $release)" -ForegroundColor Green
    } elseif ($release -ge 394802) {
        Write-Host "  [WARN] .NET Framework 4.6.2 (Release: $release)" -ForegroundColor Yellow
        $warnings += ".NET Framework version may be too low"
    } else {
        Write-Host "  [ERROR] .NET Framework version too low (Release: $release)" -ForegroundColor Red
        $issues += ".NET Framework version too low"
    }
} catch {
    Write-Host "  [WARN] Cannot detect .NET Framework version" -ForegroundColor Yellow
    $warnings += "Cannot detect .NET Framework version"
}
Write-Host ""

# 4. Check WebView2 Runtime
Write-Host "[4/6] Checking WebView2 Runtime..." -ForegroundColor Yellow
$webView2Paths = @(
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
)
$webView2Found = $false
foreach ($path in $webView2Paths) {
    if (Test-Path $path) {
        try {
            $pv = (Get-ItemProperty $path -ErrorAction Stop).pv
            if ($pv) {
                Write-Host "  [OK] WebView2 Runtime installed: $pv" -ForegroundColor Green
                $webView2Found = $true
                break
            }
        } catch {}
    }
}
if (-not $webView2Found) {
    Write-Host "  [WARN] WebView2 Runtime not installed" -ForegroundColor Yellow
    Write-Host "         Download: https://developer.microsoft.com/en-us/microsoft-edge/webview2/" -ForegroundColor Gray
    $warnings += "WebView2 Runtime not installed"
}
Write-Host ""

# 5. Check Visual C++ Redistributable
Write-Host "[5/6] Checking Visual C++ Redistributable..." -ForegroundColor Yellow
$vcppPaths = @(
    "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
)
$vcppFound = $false
foreach ($path in $vcppPaths) {
    if (Test-Path $path) {
        try {
            $installed = (Get-ItemProperty $path -ErrorAction Stop).Installed
            if ($installed -eq 1) {
                Write-Host "  [OK] VC++ Redistributable x64 installed" -ForegroundColor Green
                $vcppFound = $true
                break
            }
        } catch {}
    }
}
if (-not $vcppFound) {
    Write-Host "  [WARN] VC++ Redistributable x64 not detected" -ForegroundColor Yellow
    Write-Host "         Download: https://aka.ms/vs/17/release/vc_redist.x64.exe" -ForegroundColor Gray
    $warnings += "VC++ Redistributable x64 not detected"
}
Write-Host ""

# 6. Check admin privileges
Write-Host "[6/6] Checking admin privileges..." -ForegroundColor Yellow
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Write-Host "  [OK] Running with admin privileges" -ForegroundColor Green
} else {
    Write-Host "  [INFO] Not running as admin - Hardware monitoring requires admin" -ForegroundColor Gray
}
Write-Host ""

# Summary
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   Diagnostic Complete" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if ($issues.Count -eq 0 -and $warnings.Count -eq 0) {
    Write-Host "[OK] All checks passed, Comfyui-Box should work correctly" -ForegroundColor Green
} else {
    if ($issues.Count -gt 0) {
        Write-Host "Issues found:" -ForegroundColor Red
        for ($i = 0; $i -lt $issues.Count; $i++) {
            Write-Host "  $($i+1). $($issues[$i])" -ForegroundColor Red
        }
        Write-Host ""
    }
    if ($warnings.Count -gt 0) {
        Write-Host "Warnings:" -ForegroundColor Yellow
        for ($i = 0; $i -lt $warnings.Count; $i++) {
            Write-Host "  $($i+1). $($warnings[$i])" -ForegroundColor Yellow
        }
        Write-Host ""
    }
}

Write-Host "If Comfyui-Box fails to start, try:" -ForegroundColor White
Write-Host "  1. Install WebView2 Runtime (recommended)" -ForegroundColor Gray
Write-Host "  2. Install Visual C++ Redistributable" -ForegroundColor Gray
Write-Host "  3. Run Comfyui-Box.exe as Administrator" -ForegroundColor Gray
Write-Host "  4. Check antivirus software" -ForegroundColor Gray
Write-Host ""

Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
