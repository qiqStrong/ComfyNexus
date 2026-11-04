<#
.SYNOPSIS
    Comfyui-Box Windows System Dependency Checker
.DESCRIPTION
    Check Windows system dependencies required by Comfyui-Box
    No Python required, can run directly
#>

param(
    [switch]$Detailed
)

$ErrorActionPreference = "SilentlyContinue"

$script:PassedCount = 0
$script:FailedCount = 0
$script:WarningCount = 0
$script:Results = @()

function Add-Result {
    param(
        [string]$Name,
        [string]$Category,
        [bool]$Passed,
        [bool]$Required,
        [string]$Message,
        [string]$Details = ""
    )
    
    $script:Results += [PSCustomObject]@{
        Name = $Name
        Category = $Category
        Passed = $Passed
        Required = $Required
        Message = $Message
        Details = $Details
    }
    
    if ($Passed) {
        $script:PassedCount++
    } elseif ($Required) {
        $script:FailedCount++
    } else {
        $script:WarningCount++
    }
}

function Write-Header {
    param([string]$Title)
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " $Title" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}

function Test-WindowsVersion {
    Write-Header "System Information"
    
    $osInfo = Get-CimInstance -ClassName Win32_OperatingSystem
    $winVersion = [Environment]::OSVersion.Version
    $build = $winVersion.Build
    
    Write-Host "OS: $($osInfo.Caption)"
    Write-Host "Version: $($winVersion.ToString())"
    Write-Host "Build: $build"
    Write-Host "Architecture: $env:PROCESSOR_ARCHITECTURE"
    
    $minBuild = 17134
    
    if ($build -ge $minBuild) {
        Add-Result -Name "Windows Version" -Category "System" -Passed $true -Required $true `
            -Message "Windows 10 1803+ (Build $build)"
    } else {
        Add-Result -Name "Windows Version" -Category "System" -Passed $false -Required $true `
            -Message "Too old, need Windows 10 1803+ (Build $minBuild+)" `
            -Details "Current Build: $build"
    }
}

function Test-SystemDLLs {
    Write-Header "Windows System DLLs"
    
    $system32 = Join-Path $env:SystemRoot "System32"
    
    $dlls = @(
        @{Name = "kernel32.dll"; Required = $true; Desc = "Process management, file operations"},
        @{Name = "user32.dll"; Required = $true; Desc = "Window management"},
        @{Name = "shell32.dll"; Required = $true; Desc = "Shell operations, permission check"},
        @{Name = "shcore.dll"; Required = $true; Desc = "DPI awareness"},
        @{Name = "gdi32.dll"; Required = $true; Desc = "Graphics device interface"},
        @{Name = "dwmapi.dll"; Required = $false; Desc = "Window rounded corners (Win11)"}
    )
    
    foreach ($dll in $dlls) {
        $dllPath = Join-Path $system32 $dll.Name
        
        if (Test-Path $dllPath) {
            $fileInfo = Get-Item $dllPath
            Add-Result -Name $dll.Name -Category "SystemDLL" -Passed $true -Required $dll.Required `
                -Message "Exists ($($dll.Desc))" `
                -Details "Path: $dllPath, Size: $($fileInfo.Length) bytes"
        } else {
            Add-Result -Name $dll.Name -Category "SystemDLL" -Passed $false -Required $dll.Required `
                -Message "Not found ($($dll.Desc))" `
                -Details "Expected: $dllPath"
        }
    }
}

function Test-WindowsAPI {
    Write-Header "Windows API Function Tests"
    
    Add-Type -TypeDefinition @"
    using System;
    using System.Runtime.InteropServices;
    
    public class WinAPI {
        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern IntPtr CreateMutex(IntPtr lpMutexAttributes, bool bInitialOwner, string lpName);
        
        [DllImport("kernel32.dll")]
        public static extern bool ReleaseMutex(IntPtr hMutex);
        
        [DllImport("kernel32.dll")]
        public static extern bool CloseHandle(IntPtr hObject);
        
        [DllImport("kernel32.dll")]
        public static extern uint GetLastError();
        
        [DllImport("user32.dll")]
        public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
        
        [DllImport("user32.dll")]
        public static extern bool SetForegroundWindow(IntPtr hWnd);
        
        [DllImport("user32.dll")]
        public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
        
        [DllImport("user32.dll")]
        public static extern int GetSystemMetrics(int nIndex);
        
        [DllImport("shell32.dll")]
        public static extern bool IsUserAnAdmin();
    }
"@
    
    $apiTests = @(
        @{Name = "kernel32.CreateMutex"; Required = $true},
        @{Name = "kernel32.ReleaseMutex"; Required = $true},
        @{Name = "kernel32.CloseHandle"; Required = $true},
        @{Name = "kernel32.GetLastError"; Required = $true},
        @{Name = "user32.FindWindow"; Required = $true},
        @{Name = "user32.SetForegroundWindow"; Required = $true},
        @{Name = "user32.ShowWindow"; Required = $true},
        @{Name = "user32.GetSystemMetrics"; Required = $true},
        @{Name = "shell32.IsUserAnAdmin"; Required = $true}
    )
    
    foreach ($api in $apiTests) {
        try {
            $parts = $api.Name.Split(".")
            $className = $parts[0]
            $methodName = $parts[1]
            
            if ($className -eq "kernel32") {
                switch ($methodName) {
                    "CreateMutex" { [WinAPI]::CreateMutex([IntPtr]::Zero, $false, "TestMutex") | Out-Null }
                    "ReleaseMutex" { [WinAPI]::ReleaseMutex([IntPtr]::Zero) | Out-Null }
                    "CloseHandle" { [WinAPI]::CloseHandle([IntPtr]::Zero) | Out-Null }
                    "GetLastError" { [WinAPI]::GetLastError() | Out-Null }
                }
            } elseif ($className -eq "user32") {
                switch ($methodName) {
                    "FindWindow" { [WinAPI]::FindWindow($null, $null) | Out-Null }
                    "SetForegroundWindow" { [WinAPI]::SetForegroundWindow([IntPtr]::Zero) | Out-Null }
                    "ShowWindow" { [WinAPI]::ShowWindow([IntPtr]::Zero, 0) | Out-Null }
                    "GetSystemMetrics" { [WinAPI]::GetSystemMetrics(0) | Out-Null }
                }
            } elseif ($className -eq "shell32") {
                [WinAPI]::IsUserAnAdmin() | Out-Null
            }
            
            Add-Result -Name $api.Name -Category "WindowsAPI" -Passed $true -Required $api.Required `
                -Message "Function available"
        } catch {
            Add-Result -Name $api.Name -Category "WindowsAPI" -Passed $false -Required $api.Required `
                -Message "Function unavailable: $($_.Exception.Message)"
        }
    }
}

function Test-PowerShell {
    Write-Header "PowerShell"
    
    $psVersion = $PSVersionTable.PSVersion.ToString()
    
    Add-Result -Name "PowerShell" -Category "SystemComponent" -Passed $true -Required $true `
        -Message "Version $psVersion"
}

function Test-WebView2Runtime {
    Write-Header "EdgeWebView2 Runtime"
    
    $registryPaths = @(
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    )
    
    $found = $false
    $version = $null
    $location = $null
    
    foreach ($path in $registryPaths) {
        if (Test-Path $path) {
            try {
                $version = (Get-ItemProperty -Path $path -Name "pv" -ErrorAction SilentlyContinue).pv
                $location = (Get-ItemProperty -Path $path -Name "location" -ErrorAction SilentlyContinue).location
                if ($version) {
                    $found = $true
                    break
                }
            } catch {}
        }
    }
    
    if (-not $found) {
        $webview2Path = Join-Path ${env:ProgramFiles(x86)} "Microsoft\EdgeWebView\Application"
        if (Test-Path $webview2Path) {
            $versions = Get-ChildItem $webview2Path -Directory
            if ($versions.Count -gt 0) {
                $version = $versions[0].Name
                $found = $true
            }
        }
    }
    
    if ($found -and $version) {
        Add-Result -Name "EdgeWebView2 Runtime" -Category "Runtime" -Passed $true -Required $true `
            -Message "Version $version"
    } else {
        Add-Result -Name "EdgeWebView2 Runtime" -Category "Runtime" -Passed $false -Required $true `
            -Message "Not installed" `
            -Details "Download from: https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
    }
}

function Test-DotNetRuntime {
    Write-Header ".NET Runtime"
    
    $dotnetPath = Join-Path $env:ProgramFiles "dotnet\dotnet.exe"
    
    if (Test-Path $dotnetPath) {
        try {
            $version = & $dotnetPath --version 2>$null
            Add-Result -Name ".NET Runtime" -Category "Runtime" -Passed $true -Required $false `
                -Message "Version $version"
        } catch {
            Add-Result -Name ".NET Runtime" -Category "Runtime" -Passed $false -Required $false `
                -Message "Cannot get version"
        }
    } else {
        Add-Result -Name ".NET Runtime" -Category "Runtime" -Passed $false -Required $false `
            -Message "Not installed"
    }
}

function Test-AdminPrivileges {
    Write-Header "Administrator Privileges"
    
    try {
        $isAdmin = [WinAPI]::IsUserAnAdmin()
        if ($isAdmin) {
            Add-Result -Name "Admin Rights" -Category "Permission" -Passed $true -Required $false `
                -Message "Running as Administrator" -Details "Hardware sensor monitoring available"
        } else {
            Add-Result -Name "Admin Rights" -Category "Permission" -Passed $false -Required $false `
                -Message "Not running as Administrator" -Details "Hardware sensor monitoring will be unavailable"
        }
    } catch {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        
        if ($isAdmin) {
            Add-Result -Name "Admin Rights" -Category "Permission" -Passed $true -Required $false `
                -Message "Running as Administrator"
        } else {
            Add-Result -Name "Admin Rights" -Category "Permission" -Passed $false -Required $false `
                -Message "Not running as Administrator"
        }
    }
}

function Test-WMIService {
    Write-Header "WMI Service"
    
    try {
        $service = Get-Service -Name Winmgmt -ErrorAction Stop
        if ($service.Status -eq "Running") {
            Add-Result -Name "WMI Service" -Category "SystemService" -Passed $true -Required $false `
                -Message "Running"
        } else {
            Add-Result -Name "WMI Service" -Category "SystemService" -Passed $false -Required $false `
                -Message "Not running (Status: $($service.Status))"
        }
    } catch {
        Add-Result -Name "WMI Service" -Category "SystemService" -Passed $false -Required $false `
            -Message "Check failed: $($_.Exception.Message)"
    }
}

function Test-SystemIntegrity {
    Write-Header "System Integrity Check"
    
    $criticalFiles = @(
        @{Path = "$env:SystemRoot\System32\cmd.exe"; Name = "Command Prompt"},
        @{Path = "$env:SystemRoot\System32\reg.exe"; Name = "Registry Tool"},
        @{Path = "$env:SystemRoot\System32\sc.exe"; Name = "Service Control Manager"},
        @{Path = "$env:SystemRoot\System32\netsh.exe"; Name = "Network Config Tool"}
    )
    
    foreach ($file in $criticalFiles) {
        $resolvedPath = $ExecutionContext.InvokeCommand.ExpandString($file.Path)
        if (Test-Path $resolvedPath) {
            Add-Result -Name $file.Name -Category "SystemTools" -Passed $true -Required $true `
                -Message "Exists"
        } else {
            Add-Result -Name $file.Name -Category "SystemTools" -Passed $false -Required $true `
                -Message "Missing" -Details "Path: $resolvedPath"
        }
    }
}

function Test-NetworkStack {
    Write-Header "Network Features"
    
    try {
        $tcpTest = New-Object System.Net.Sockets.TcpClient
        Add-Result -Name "TCP/IP Stack" -Category "Network" -Passed $true -Required $true `
            -Message "Available"
        $tcpTest.Close()
    } catch {
        Add-Result -Name "TCP/IP Stack" -Category "Network" -Passed $false -Required $true `
            -Message "Error: $($_.Exception.Message)"
    }
    
    try {
        $cert = [System.Security.Cryptography.X509Certificates.X509Certificate]::new()
        Add-Result -Name "SSL/TLS" -Category "Network" -Passed $true -Required $true `
            -Message "Available"
    } catch {
        Add-Result -Name "SSL/TLS" -Category "Network" -Passed $false -Required $true `
            -Message "Error: $($_.Exception.Message)"
    }
}

function Write-Summary {
    Write-Header "Summary"
    
    $total = $script:Results.Count
    $requiredResults = $script:Results | Where-Object { $_.Required }
    $requiredPassed = ($requiredResults | Where-Object { $_.Passed }).Count
    $requiredTotal = $requiredResults.Count
    
    Write-Host ""
    Write-Host "Total checks: $total"
    Write-Host "  [PASS] Passed: $script:PassedCount" -ForegroundColor Green
    Write-Host "  [FAIL] Failed (Required): $script:FailedCount" -ForegroundColor Red
    Write-Host "  [WARN] Failed (Optional): $script:WarningCount" -ForegroundColor Yellow
    
    Write-Host ""
    Write-Host "Required items: $requiredPassed/$requiredTotal"
    
    if ($script:FailedCount -gt 0) {
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Red
        Write-Host " The following REQUIRED components failed:" -ForegroundColor Red
        Write-Host "============================================================" -ForegroundColor Red
        
        $script:Results | Where-Object { -not $_.Passed -and $_.Required } | ForEach-Object {
            Write-Host "  - $($_.Name): $($_.Message)" -ForegroundColor Red
            if ($_.Details) {
                Write-Host "    $($_.Details)" -ForegroundColor DarkGray
            }
        }
        
        Write-Host ""
        Write-Host "Suggested actions:" -ForegroundColor Yellow
        Write-Host "  1. Make sure you are using a full Windows system (not a Lite version)"
        Write-Host "  2. Install EdgeWebView2 Runtime: https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
        Write-Host "  3. Run system file check: sfc /scannow"
        Write-Host "  4. Install latest Windows updates"
        
        return $false
    } else {
        Write-Host ""
        Write-Host "All required components passed!" -ForegroundColor Green
        
        if ($script:WarningCount -gt 0) {
            Write-Host ""
            Write-Host "The following optional components are not installed:" -ForegroundColor Yellow
            Write-Host "(Core functionality is not affected)" -ForegroundColor Yellow
            $script:Results | Where-Object { -not $_.Passed -and -not $_.Required } | ForEach-Object {
                Write-Host "  - $($_.Name): $($_.Message)" -ForegroundColor Yellow
            }
        }
        
        return $true
    }
}

function Show-DetailedResults {
    if (-not $Detailed) { return }
    
    Write-Header "Detailed Results"
    
    $script:Results | ForEach-Object {
        $status = if ($_.Passed) { "[PASS]" } elseif ($_.Required) { "[FAIL]" } else { "[WARN]" }
        $reqStr = if ($_.Required) { "[Required]" } else { "[Optional]" }
        $color = if ($_.Passed) { "Green" } elseif ($_.Required) { "Red" } else { "Yellow" }
        
        Write-Host "$status $reqStr $($_.Name): $($_.Message)" -ForegroundColor $color
        if ($_.Details) {
            Write-Host "      $($_.Details)" -ForegroundColor DarkGray
        }
    }
}

function Main {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " Comfyui-Box Windows System Dependency Checker" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    
    Test-WindowsVersion
    Test-SystemDLLs
    Test-WindowsAPI
    Test-PowerShell
    Test-WebView2Runtime
    Test-DotNetRuntime
    Test-AdminPrivileges
    Test-WMIService
    Test-SystemIntegrity
    Test-NetworkStack
    
    Show-DetailedResults
    $success = Write-Summary
    
    Write-Host ""
    Write-Host "Press any key to exit..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    
    return $success
}

Main
