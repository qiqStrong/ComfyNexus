# Comfyui-Box 前端构建脚本
# 用途: 只构建前端
# 使用方法: .\build_frontend.ps1

$ErrorActionPreference = "Stop"

# 获取项目根目录
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $ProjectRoot "frontend"

Write-Host "Comfyui-Box 前端构建" -ForegroundColor Cyan
Write-Host ""

try {
    Push-Location $FrontendDir
    
    Write-Host "检查依赖..." -ForegroundColor Yellow
    if (-not (Test-Path "node_modules")) {
        Write-Host "安装依赖..." -ForegroundColor Yellow
        npm install
        if ($LASTEXITCODE -ne 0) {
            throw "npm install 失败"
        }
    }
    
    Write-Host "构建前端..." -ForegroundColor Yellow
    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "前端构建失败"
    }
    
    Write-Host ""
    Write-Host "✓ 前端构建完成" -ForegroundColor Green
    
    # 显示构建产物
    $DistDir = Join-Path $ProjectRoot "dist"
    if (Test-Path $DistDir) {
        $Files = Get-ChildItem -Path $DistDir -Recurse -File
        $TotalSize = ($Files | Measure-Object -Property Length -Sum).Sum / 1MB
        Write-Host "构建产物: $($Files.Count) 个文件, $([math]::Round($TotalSize, 2)) MB" -ForegroundColor Blue
        Write-Host "输出目录: $DistDir" -ForegroundColor Blue
    }
    
} catch {
    Write-Host ""
    Write-Host "✗ 前端构建失败: $_" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}
