# Comfyui-Box 后端打包脚本
# 用途: 只打包后端（需要先构建前端）
# 使用方法: .\build_backend.ps1 [-Version "1.0.2"] [-Clean]

param(
    [Parameter(Mandatory=$false)]
    [string]$Version = "",
    
    [Parameter(Mandatory=$false)]
    [switch]$Clean = $false
)

$ErrorActionPreference = "Stop"

# 导入公共函数库
. "$PSScriptRoot\构建工具库.ps1"

# 获取版本号
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Get-ProjectVersion
}

# 获取项目根目录
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv"
$TempDistDir = Join-Path $ProjectRoot "dist"

# 构建产物目录
$BuildOutputDir = Join-Path $PSScriptRoot "打包产物_$Version"
$DistDir = Join-Path $BuildOutputDir "dist"
$BuildDir = Join-Path $BuildOutputDir "build"

Write-Host "Comfyui-Box 后端打包" -ForegroundColor Cyan
Write-Host ""
Write-Host "版本: $Version" -ForegroundColor Yellow
Write-Host "构建产物目录: $BuildOutputDir" -ForegroundColor Yellow
Write-Host ""

try {
    # 检查前端构建产物
    if (-not (Test-Path $TempDistDir)) {
        Write-Host "✗ 前端构建产物不存在" -ForegroundColor Red
        Write-Host "请先运行: .\build_frontend.ps1" -ForegroundColor Yellow
        exit 1
    }
    
    # 检查虚拟环境
    if (-not (Test-Path $VenvDir)) {
        Write-Host "✗ Python 虚拟环境不存在" -ForegroundColor Red
        Write-Host "请先创建虚拟环境: python -m venv .venv" -ForegroundColor Yellow
        exit 1
    }
    
    # 检查 PyInstaller
    $PyInstaller = Join-Path $VenvDir "Scripts\pyinstaller.exe"
    if (-not (Test-Path $PyInstaller)) {
        Write-Host "✗ PyInstaller 未安装" -ForegroundColor Red
        Write-Host "请先安装: .venv\Scripts\activate ; pip install pyinstaller" -ForegroundColor Yellow
        exit 1
    }
    
    # 创建构建产物目录
    if (-not (Test-Path $BuildOutputDir)) {
        New-Item -ItemType Directory -Path $BuildOutputDir -Force | Out-Null
        Write-Host "创建构建产物目录" -ForegroundColor Yellow
    }
    
    Write-Host "运行 PyInstaller..." -ForegroundColor Yellow
    
    Push-Location $ProjectRoot
    
    if ($Clean) {
        & $PyInstaller "build_exe.spec" --clean --distpath $DistDir --workpath $BuildDir
    } else {
        & $PyInstaller "build_exe.spec" --distpath $DistDir --workpath $BuildDir
    }
    
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 打包失败"
    }
    
    Pop-Location
    
    Write-Host ""
    Write-Host "✓ 后端打包完成" -ForegroundColor Green
    
    # 显示 exe 信息
    $ExePath = Join-Path $DistDir "Comfyui-Box.exe"
    if (Test-Path $ExePath) {
        $ExeSize = (Get-Item $ExePath).Length / 1MB
        Write-Host "exe 文件: Comfyui-Box.exe ($([math]::Round($ExeSize, 2)) MB)" -ForegroundColor Blue
        Write-Host "路径: $ExePath" -ForegroundColor Blue
    }
    
} catch {
    Write-Host ""
    Write-Host "✗ 后端打包失败: $_" -ForegroundColor Red
    exit 1
}
