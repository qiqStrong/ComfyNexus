# Comfyui-Box 快速构建脚本
# 用途: 快速构建（跳过测试和清理）
# 使用方法: .\quick_build.ps1 [-Version "1.0.2"] [-SkipFrontend] [-ShowConsole]

param(
    [Parameter(Mandatory=$false)]
    [string]$Version = "",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipFrontend = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$ShowConsole = $false
)

# 设置错误处理
$ErrorActionPreference = "Stop"

# 导入公共函数库
. "$PSScriptRoot\构建工具库.ps1"

# 如果未指定版本号，从 VERSION 文件读取
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Get-ProjectVersion
}

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                           ║" -ForegroundColor Cyan
Write-Host "║              Comfyui-Box 快速构建脚本                      ║" -ForegroundColor Cyan
Write-Host "║                                                           ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

Write-Host "版本: $Version" -ForegroundColor Yellow
Write-Host "打包模式: $(if ($ShowConsole) { '调试模式（显示控制台）' } else { '生产模式（隐藏控制台）' })" -ForegroundColor $(if ($ShowConsole) { 'Yellow' } else { 'Green' })
Write-Host "跳过前端构建: $SkipFrontend" -ForegroundColor Yellow
Write-Host "跳过测试: 是" -ForegroundColor Yellow
Write-Host "跳过清理: 是" -ForegroundColor Yellow
Write-Host ""

try {
    # 调用完整构建脚本，跳过测试和清理
    if ($SkipFrontend) {
        & "$PSScriptRoot\构建.ps1" -Version $Version -SkipTests -SkipClean -SkipFrontend -ShowConsole:$ShowConsole
    } else {
        & "$PSScriptRoot\构建.ps1" -Version $Version -SkipTests -SkipClean -ShowConsole:$ShowConsole
    }
    
    if ($LASTEXITCODE -ne 0) {
        throw "构建失败"
    }
    
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║                                                           ║" -ForegroundColor Green
    Write-Host "║                    快速构建完成！                         ║" -ForegroundColor Green
    Write-Host "║                                                           ║" -ForegroundColor Green
    Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Red
    Write-Host "║                                                           ║" -ForegroundColor Red
    Write-Host "║                    快速构建失败！                         ║" -ForegroundColor Red
    Write-Host "║                                                           ║" -ForegroundColor Red
    Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Red
    Write-Host ""
    Write-Host "错误信息: $_" -ForegroundColor Red
    Write-Host ""
    
    # 暂停等待用户按键
    pause
    exit 1
}

# 暂停等待用户按键
pause
