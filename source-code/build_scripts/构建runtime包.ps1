# Comfyui-Box Runtime 包构建脚本
# 用途: 下载并打包完整运行时依赖，供精简版 Windows 用户使用
# 使用: .\构建runtime包.ps1 [-OutputDir <输出目录>]
#
# 生成的 runtime 包结构:
#   runtime/
#   ├── webview2/        ← WebView2 Fixed Version (~100MB)
#   ├── dotnet8/         ← .NET 8 Desktop Runtime (~60-80MB)
#   └── vcruntime/       ← VC++ Runtime 2015-2022 (~2MB)
#
# 用户只需将此包解压到 Comfyui-Box 安装目录（与 Comfyui-Box.exe 同级）即可

param(
    [string]$OutputDir = "",
    [string]$WebView2Version = "131.0.2903.99",
    [string]$DotNetVersion = "8.0.13",
    [switch]$SkipDownload = $false
)

$ErrorActionPreference = "Stop"

# ============================================
# 工具函数
# ============================================

function Write-Step {
    param([string]$Message)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "  [..] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "  [!!] $Message" -ForegroundColor Red
}

function Download-File {
    param(
        [string]$Url,
        [string]$Output,
        [string]$Description = ""
    )

    if (Test-Path $Output) {
        Write-Success "$Description 已存在，跳过下载"
        return $true
    }

    Write-Info "下载 $Description ..."
    Write-Info "  URL: $Url"
    Write-Info "  保存到: $Output"

    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $Url -OutFile $Output -UseBasicParsing
        $ProgressPreference = 'Continue'
        $fileSize = (Get-Item $Output).Length / 1MB
        Write-Success "$Description 下载完成 ($([math]::Round($fileSize, 1)) MB)"
        return $true
    }
    catch {
        Write-Err "$Description 下载失败: $_"
        if (Test-Path $Output) { Remove-Item $Output -Force -ErrorAction SilentlyContinue }
        return $false
    }
}

# ============================================
# 初始化
# ============================================

$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not $OutputDir) {
    $OutputDir = Join-Path $projectRoot "build_output"
}

$runtimeDir = Join-Path $OutputDir "runtime"
$tempDir = Join-Path $OutputDir "runtime_temp"

Write-Step "Comfyui-Box Runtime 包构建"

Write-Host "  项目根目录: $projectRoot"
Write-Host "  输出目录: $OutputDir"
Write-Host "  Runtime 目录: $runtimeDir"
Write-Host ""

if (Test-Path $tempDir) {
    Remove-Item $tempDir -Recurse -Force
}
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

# ============================================
# 步骤 1: WebView2 Fixed Version
# ============================================

Write-Step "步骤 1/3: 下载 WebView2 Fixed Version"

$webview2Dir = Join-Path $runtimeDir "webview2"
$webview2Marker = Join-Path $webview2Dir "msedge.dll"

if (Test-Path $webview2Marker) {
    Write-Success "WebView2 Fixed Version 已存在，跳过"
}
elseif ($SkipDownload) {
    Write-Info "跳过下载（-SkipDownload 模式）"
}
else {
    $webview2Zip = Join-Path $tempDir "webview2_fixed.zip"
    $webview2Url = "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/7e91e4f2-5d2a-4e5f-9c3d-8e0b3c4d5e6f/Microsoft.WebView2.FixedVersionRuntime.$WebView2Version.x64.cab"

    # 微软官方 Fixed Version 下载链接（x64）
    # 实际链接需要从 https://developer.microsoft.com/en-us/microsoft-edge/webview2/ 获取
    # 这里使用通用链接格式
    $webview2Url = "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/Microsoft.WebView2.FixedVersionRuntime.$WebView2Version.x64.zip"

    $downloaded = Download-File -Url $webview2Url -Output $webview2Zip -Description "WebView2 Fixed Version $WebView2Version (x64)"

    if (-not $downloaded) {
        Write-Err "WebView2 Fixed Version 下载失败"
        Write-Info "请手动下载："
        Write-Info "  1. 访问 https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
        Write-Info "  2. 下载 Fixed Version (x64)"
        Write-Info "  3. 解压到 $webview2Dir"
        Write-Info "  4. 确保 $webview2Dir\msedge.dll 存在"
        Write-Info "  5. 重新运行此脚本（使用 -SkipDownload 跳过已下载的文件）"
    }
    else {
        Write-Info "解压 WebView2 Fixed Version ..."
        try {
            Expand-Archive -Path $webview2Zip -DestinationPath $tempDir -Force

            # Fixed Version ZIP 通常包含一个子目录，需要找到正确的目录
            $extractedDir = Get-ChildItem -Path $tempDir -Directory |
                Where-Object { Test-Path (Join-Path $_.FullName "msedge.dll") } |
                Select-Object -First 1

            if ($extractedDir) {
                New-Item -ItemType Directory -Path (Split-Path $webview2Dir -Parent) -Force | Out-Null
                Move-Item -Path $extractedDir.FullName -Destination $webview2Dir -Force
                Write-Success "WebView2 Fixed Version 解压完成"
            }
            else {
                # 可能在根目录
                $msedgeDll = Get-ChildItem -Path $tempDir -Filter "msedge.dll" -Recurse | Select-Object -First 1
                if ($msedgeDll) {
                    $sourceDir = $msedgeDll.DirectoryName
                    New-Item -ItemType Directory -Path (Split-Path $webview2Dir -Parent) -Force | Out-Null
                    Move-Item -Path $sourceDir -Destination $webview2Dir -Force
                    Write-Success "WebView2 Fixed Version 解压完成"
                }
                else {
                    Write-Err "解压后未找到 msedge.dll"
                }
            }
        }
        catch {
            Write-Err "WebView2 解压失败: $_"
        }
    }
}

# 验证
if (Test-Path $webview2Marker) {
    $wv2Size = (Get-ChildItem $webview2Dir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Success "WebView2 Fixed Version 就绪 ($([math]::Round($wv2Size, 1)) MB)"
}

# ============================================
# 步骤 2: .NET 8 Desktop Runtime
# ============================================

Write-Step "步骤 2/3: 下载 .NET 8 Desktop Runtime"

$dotnet8Dir = Join-Path $runtimeDir "dotnet8"
$dotnet8Marker = Join-Path $dotnet8Dir "shared\Microsoft.WindowsDesktop.App"

if (Test-Path $dotnet8Marker) {
    Write-Success ".NET 8 Desktop Runtime 已存在，跳过"
}
elseif ($SkipDownload) {
    Write-Info "跳过下载（-SkipDownload 模式）"
}
else {
    # 下载 .NET 8 Desktop Runtime 安装包
    $dotnetInstaller = Join-Path $tempDir "windowsdesktop-runtime-$DotNetVersion-win-x64.exe"
    $dotnetUrl = "https://download.visualstudio.microsoft.com/download/pr/dotnet-sdk-win-x64/dotnet-desktop-runtime-$DotNetVersion-win-x64.exe"

    # 使用官方下载链接
    $dotnetUrl = "https://aka.ms/dotnet/8.0/windowsdesktop-runtime-win-x64.exe"

    $downloaded = Download-File -Url $dotnetUrl -Output $dotnetInstaller -Description ".NET 8 Desktop Runtime Installer"

    if (-not $downloaded) {
        Write-Err ".NET 8 Desktop Runtime 下载失败"
        Write-Info "请手动安装后复制文件："
        Write-Info "  1. 安装 .NET 8 Desktop Runtime"
        Write-Info "  2. 复制 C:\Program Files\dotnet\shared 到 $dotnet8Dir\shared"
        Write-Info "  3. 复制 C:\Program Files\dotnet\host 到 $dotnet8Dir\host"
    }
    else {
        Write-Info "提取 .NET 8 运行时文件 ..."

        # 方案 A：使用 /install /layout 提取文件（不需要安装）
        $layoutDir = Join-Path $tempDir "dotnet_layout"
        New-Item -ItemType Directory -Path $layoutDir -Force | Out-Null

        try {
            # 尝试使用 /layout 参数提取
            Write-Info "  尝试 /layout 提取 ..."
            $proc = Start-Process -FilePath $dotnetInstaller -ArgumentList "/layout", $layoutDir, "/passive" -NoNewWindow -Wait -PassThru

            # /layout 可能不支持，回退到安装后复制
            if ($proc.ExitCode -ne 0) {
                Write-Info "  /layout 不支持，使用安装后复制方案"
            }
        }
        catch {
            Write-Info "  /layout 失败，使用安装后复制方案"
        }

        # 方案 B：从已安装的系统复制
        $systemDotnet = Join-Path $env:ProgramFiles "dotnet"
        if (Test-Path (Join-Path $systemDotnet "shared\Microsoft.WindowsDesktop.App")) {
            Write-Info "  从系统安装目录复制 ..."

            New-Item -ItemType Directory -Path $dotnet8Dir -Force | Out-Null

            # 复制 shared 目录（只复制 8.x 版本）
            $sharedDir = Join-Path $dotnet8Dir "shared"
            New-Item -ItemType Directory -Path $sharedDir -Force | Out-Null

            # Microsoft.WindowsDesktop.App
            $srcDesktop = Join-Path $systemDotnet "shared\Microsoft.WindowsDesktop.App"
            $dstDesktop = Join-Path $sharedDir "Microsoft.WindowsDesktop.App"
            New-Item -ItemType Directory -Path $dstDesktop -Force | Out-Null

            Get-ChildItem $srcDesktop -Directory | Where-Object { $_.Name -like "8.*" } | ForEach-Object {
                Write-Info "  复制 Microsoft.WindowsDesktop.App\$($_.Name) ..."
                Copy-Item -Path $_.FullName -Destination $dstDesktop -Recurse -Force
            }

            # Microsoft.NETCore.App
            $srcNetCore = Join-Path $systemDotnet "shared\Microsoft.NETCore.App"
            $dstNetCore = Join-Path $sharedDir "Microsoft.NETCore.App"
            New-Item -ItemType Directory -Path $dstNetCore -Force | Out-Null

            Get-ChildItem $srcNetCore -Directory | Where-Object { $_.Name -like "8.*" } | ForEach-Object {
                Write-Info "  复制 Microsoft.NETCore.App\$($_.Name) ..."
                Copy-Item -Path $_.FullName -Destination $dstNetCore -Recurse -Force
            }

            # host 目录
            $srcHost = Join-Path $systemDotnet "host"
            $dstHost = Join-Path $dotnet8Dir "host"
            if (Test-Path $srcHost) {
                Write-Info "  复制 host 目录 ..."
                Copy-Item -Path $srcHost -Destination $dstHost -Recurse -Force
            }

            # dotnet.exe
            $dotnetExe = Join-Path $systemDotnet "dotnet.exe"
            if (Test-Path $dotnetExe) {
                Copy-Item -Path $dotnetExe -Destination $dotnet8Dir -Force
            }

            Write-Success ".NET 8 Desktop Runtime 复制完成"
        }
        else {
            Write-Err "系统中未安装 .NET 8 Desktop Runtime，无法复制"
            Write-Info "请先安装 .NET 8 Desktop Runtime 后重新运行此脚本"
        }
    }
}

# 验证
if (Test-Path $dotnet8Marker) {
    $dn8Size = (Get-ChildItem $dotnet8Dir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Success ".NET 8 Desktop Runtime 就绪 ($([math]::Round($dn8Size, 1)) MB)"
}

# ============================================
# 步骤 3: VC++ Runtime DLLs
# ============================================

Write-Step "步骤 3/3: 提取 VC++ Runtime DLLs"

$vcruntimeDir = Join-Path $runtimeDir "vcruntime"
$vcruntimeMarker = Join-Path $vcruntimeDir "vcruntime140.dll"

if (Test-Path $vcruntimeMarker) {
    Write-Success "VC++ Runtime 已存在，跳过"
}
else {
    # 直接从系统 System32 复制
    $system32 = Join-Path $env:SystemRoot "System32"
    $requiredDlls = @(
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "concrt140.dll"
    )

    New-Item -ItemType Directory -Path $vcruntimeDir -Force | Out-Null

    $copiedCount = 0
    foreach ($dll in $requiredDlls) {
        $src = Join-Path $system32 $dll
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination $vcruntimeDir -Force
            $copiedCount++
        }
        else {
            Write-Info "  $dll 不存在于 System32，跳过"
        }
    }

    if ($copiedCount -gt 0) {
        Write-Success "VC++ Runtime 复制完成 ($copiedCount 个 DLL)"
    }
    else {
        Write-Err "未找到 VC++ Runtime DLLs"
        Write-Info "请安装 VC++ Redistributable 后重新运行此脚本"
        Write-Info "  下载: https://aka.ms/vs/17/release/vc_redist.x64.exe"
    }
}

# 验证
if (Test-Path $vcruntimeMarker) {
    $vcSize = (Get-ChildItem $vcruntimeDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Success "VC++ Runtime 就绪 ($([math]::Round($vcSize, 1)) MB)"
}

# ============================================
# 清理临时文件
# ============================================

Write-Step "清理临时文件"

if (Test-Path $tempDir) {
    Remove-Item $tempDir -Recurse -Force
    Write-Success "临时目录已清理"
}

# ============================================
# 打包
# ============================================

Write-Step "打包 Runtime 补丁包"

$zipFileName = "Comfyui-Box_Runtime_Patch.zip"
$zipPath = Join-Path $OutputDir $zipFileName

if (Test-Path $runtimeDir) {
    if (Test-Path $zipPath) {
        Remove-Item $zipPath -Force
    }

    Write-Info "压缩 runtime 目录 ..."
    Compress-Archive -Path $runtimeDir -DestinationPath $zipPath -CompressionLevel Optimal -Force

    $zipSize = (Get-Item $zipPath).Length / 1MB
    Write-Success "Runtime 补丁包已创建: $zipPath ($([math]::Round($zipSize, 1)) MB)"
}

# ============================================
# 最终报告
# ============================================

Write-Step "构建报告"

$allOk = $true

if (Test-Path $webview2Marker) {
    $wv2Size = (Get-ChildItem $webview2Dir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Success "WebView2 Fixed Version: $([math]::Round($wv2Size, 1)) MB"
}
else {
    Write-Err "WebView2 Fixed Version: 缺失"
    $allOk = $false
}

if (Test-Path $dotnet8Marker) {
    $dn8Size = (Get-ChildItem $dotnet8Dir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Success ".NET 8 Desktop Runtime: $([math]::Round($dn8Size, 1)) MB"
}
else {
    Write-Err ".NET 8 Desktop Runtime: 缺失"
    $allOk = $false
}

if (Test-Path $vcruntimeMarker) {
    $vcSize = (Get-ChildItem $vcruntimeDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Success "VC++ Runtime: $([math]::Round($vcSize, 1)) MB"
}
else {
    Write-Err "VC++ Runtime: 缺失"
    $allOk = $false
}

Write-Host ""

if ($allOk) {
    $totalSize = (Get-ChildItem $runtimeDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Success "Runtime 包构建完成！"
    Write-Host ""
    Write-Host "  总大小: $([math]::Round($totalSize, 1)) MB" -ForegroundColor White
    Write-Host "  输出位置: $zipPath" -ForegroundColor White
    Write-Host ""
    Write-Host "  使用方法:" -ForegroundColor White
    Write-Host "  1. 将 $zipFileName 下载到本地" -ForegroundColor Gray
    Write-Host "  2. 解压到 Comfyui-Box 安装目录（与 Comfyui-Box.exe 同级）" -ForegroundColor Gray
    Write-Host "  3. 解压后应出现 runtime/ 目录" -ForegroundColor Gray
    Write-Host "  4. 重新启动 Comfyui-Box 即可" -ForegroundColor Gray
}
else {
    Write-Err "Runtime 包构建不完整，请检查上方错误信息"
    Write-Info "可以重新运行脚本（使用 -SkipDownload 跳过已下载的文件）"
}
