# Comfyui-Box 发布包生成脚本
# 用途: 从已有的构建产物目录创建发布包
# 使用方法: .\create_release_package.ps1 [-Version "1.0.2"] [-VerboseOutput]

param(
    [Parameter(Mandatory=$false)]
    [string]$Version = "",
    
    [Parameter(Mandatory=$false)]
    [switch]$VerboseOutput = $false
)

# 设置错误处理
$ErrorActionPreference = "Stop"

# 导入公共函数库
. "$PSScriptRoot\构建工具库.ps1"

# 获取版本号
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Get-ProjectVersion
}

# 构建产物目录
$BuildOutputDir = Join-Path $PSScriptRoot "打包产物_$Version"
$DistDir = Join-Path $BuildOutputDir "dist"

Write-Host ""
Write-ColorOutput @"
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           Comfyui-Box 发布包生成工具                       ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"@ "Cyan"
Write-Host ""
Write-Info "版本: $Version"
Write-Info "构建产物目录: $BuildOutputDir"
Write-Info "详细模式: $VerboseOutput"
Write-Host ""

try {
    # 检查构建产物目录是否存在
    if (-not (Test-Path $BuildOutputDir)) {
        throw "构建产物目录不存在: $BuildOutputDir`n请先运行构建脚本: .\build.ps1"
    }
    
    # 检查 dist 目录是否存在
    if (-not (Test-Path $DistDir)) {
        throw "dist 目录不存在: $DistDir`n请先运行构建脚本: .\build.ps1"
    }
    
    # 生成发布包
    $Result = New-ReleasePackage `
        -DistDir $DistDir `
        -Version $Version `
        -OutputDir $BuildOutputDir `
        -VerboseOutput:$VerboseOutput
    
    # 显示结果
    Write-Host ""
    Write-ColorOutput @"
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║                 发布包生成成功！                          ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"@ "Green"
    Write-Host ""
    Write-Info "文件名: $($Result.ZipName)"
    Write-Info "大小: $([math]::Round($Result.ZipSize, 2)) MB"
    Write-Info "包含文件: $($Result.FileCount) 个"
    Write-Info "ZIP 条目: $($Result.EntryCount) 个"
    Write-Info "路径: $($Result.ZipPath)"
    Write-Host ""
    
    Write-ColorOutput "下一步操作:" "Yellow"
    Write-Host "  1. 验证发布包: .\verify_build.ps1 -Version $Version"
    Write-Host "  2. 测试 exe: $DistDir\Comfyui-Box.exe"
    Write-Host "  3. 解压测试: Expand-Archive -Path '$($Result.ZipName)' -DestinationPath '.\test'"
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-ColorOutput @"
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║                 发布包生成失败！                          ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"@ "Red"
    Write-Host ""
    Write-Error-Custom "错误: $_"
    Write-Host ""
    Write-Host "Stack Trace:" -ForegroundColor Yellow
    Write-Host $_.ScriptStackTrace -ForegroundColor Gray
    Write-Host ""
    
    Write-ColorOutput "故障排查建议:" "Yellow"
    Write-Host "  1. 检查构建产物目录是否存在: Test-Path '$BuildOutputDir'"
    Write-Host "  2. 检查 dist 目录是否存在: Test-Path '$DistDir'"
    Write-Host "  3. 检查 exe 文件是否存在: Test-Path '$DistDir\Comfyui-Box.exe'"
    Write-Host "  4. 运行构建验证: .\verify_build.ps1 -Version $Version"
    Write-Host "  5. 重新构建: .\build.ps1"
    Write-Host ""
    
    exit 1
}
