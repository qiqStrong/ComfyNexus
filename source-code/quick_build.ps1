# Comfyui-Box 快速构建脚本入口
# 用途: 从项目根目录调用快速构建脚本
# 
# 使用方法:
#   .\quick_build.ps1                          # 交互式选择打包模式和其他选项
#
# 打包模式说明:
#   生产模式（默认）: 隐藏控制台窗口，适合正式发布
#   调试模式: 显示控制台窗口，方便查看日志和排查问题

# 设置错误处理
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                           ║" -ForegroundColor Cyan
Write-Host "║              Comfyui-Box 快速构建脚本                      ║" -ForegroundColor Cyan
Write-Host "║                                                           ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ============================================
# 询问 1: 选择打包模式
# ============================================
Write-Host "╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║           请选择打包模式（控制台窗口）                    ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  [1] 生产模式 - 隐藏控制台窗口" -ForegroundColor Green
Write-Host "      • 适用于正式发布" -ForegroundColor Gray
Write-Host "      • 用户看不到任何控制台输出" -ForegroundColor Gray
Write-Host "      • 界面更加专业美观" -ForegroundColor Gray
Write-Host ""
Write-Host "  [2] 调试模式 - 显示控制台窗口" -ForegroundColor Yellow
Write-Host "      • 适用于开发测试" -ForegroundColor Gray
Write-Host "      • 可以看到所有日志和错误信息" -ForegroundColor Gray
Write-Host "      • 方便排查问题" -ForegroundColor Gray
Write-Host ""

do {
    $modeResponse = Read-Host "请选择 (1/2，默认: 1)"
    
    if ([string]::IsNullOrWhiteSpace($modeResponse) -or $modeResponse -eq "1") {
        $ShowConsole = $false
        Write-Host "✓ 已选择: 生产模式（隐藏控制台）" -ForegroundColor Green
        break
    } elseif ($modeResponse -eq "2") {
        $ShowConsole = $true
        Write-Host "✓ 已选择: 调试模式（显示控制台）" -ForegroundColor Yellow
        break
    } else {
        Write-Host "✗ 无效选择，请输入 1 或 2" -ForegroundColor Red
    }
} while ($true)

Write-Host ""

# ============================================
# 询问 2: 是否跳过前端构建
# ============================================
Write-Host "是否跳过前端构建？" -ForegroundColor Cyan
Write-Host "  [1] 是 (默认，前端代码未改动，可以跳过以节省时间)" -ForegroundColor Green
Write-Host "  [2] 否 (完整构建前端)" -ForegroundColor Yellow
Write-Host ""

do {
    $frontendResponse = Read-Host "请选择 (1/2，默认: 1)"
    
    if ([string]::IsNullOrWhiteSpace($frontendResponse) -or $frontendResponse -eq "1") {
        $SkipFrontend = $true
        Write-Host "✓ 将跳过前端构建" -ForegroundColor Green
        break
    } elseif ($frontendResponse -eq "2") {
        $SkipFrontend = $false
        Write-Host "✓ 将完整构建前端" -ForegroundColor Yellow
        break
    } else {
        Write-Host "✗ 无效选择，请输入 1 或 2" -ForegroundColor Red
    }
} while ($true)

Write-Host ""

# ============================================
# 询问 3: 是否指定版本号
# ============================================
Write-Host "是否指定版本号？" -ForegroundColor Cyan
Write-Host "  直接回车: 从 comfyui_box_version.py 文件读取" -ForegroundColor Gray
Write-Host "  输入版本号: 例如 1.0.2" -ForegroundColor Gray
Write-Host ""

$versionResponse = Read-Host "请输入版本号（默认: 从 comfyui_box_version.py 文件读取）"

if ([string]::IsNullOrWhiteSpace($versionResponse)) {
    $Version = ""
    Write-Host "✓ 将从 comfyui_box_version.py 文件读取版本号" -ForegroundColor Green
} else {
    $Version = $versionResponse
    Write-Host "✓ 使用指定版本号: $Version" -ForegroundColor Green
}

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ============================================
# 调用构建脚本
# ============================================
try {
    if ($SkipFrontend) {
        & "$PSScriptRoot\build_scripts\快速构建.ps1" -Version $Version -SkipFrontend -ShowConsole:$ShowConsole
    } else {
        & "$PSScriptRoot\build_scripts\快速构建.ps1" -Version $Version -ShowConsole:$ShowConsole
    }
} catch {
    Write-Host ""
    Write-Host "构建过程中发生错误: $_" -ForegroundColor Red
    Write-Host ""
    pause
    exit 1
}
