# Comfyui-Box 构建验证脚本
# 用途: 验证构建产物的完整性
# 使用方法: .\verify_build.ps1 [-Version "1.0.2"]

param(
    [Parameter(Mandatory=$false)]
    [string]$Version = ""
)

# 设置错误处理
$ErrorActionPreference = "Stop"

# 导入公共函数库
. "$PSScriptRoot\构建工具库.ps1"

Write-Host ""
Write-ColorOutput @"
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║            Comfyui-Box 构建验证工具                        ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"@ "Cyan"
Write-Host ""

# 获取版本号
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Get-ProjectVersion
}

# 构建产物目录
$BuildOutputDir = Join-Path $PSScriptRoot "打包产物_$Version"
$DistDir = Join-Path $BuildOutputDir "dist"
$Errors = @()
$Warnings = @()

Write-Info "验证版本: $Version"
Write-Info "构建产物目录: $BuildOutputDir"
Write-Host ""

# ============================================
# 1. 验证构建产物目录
# ============================================
Write-Step "1/4: 验证构建产物目录"

if (-not (Test-Path $BuildOutputDir)) {
    $Errors += "构建产物目录不存在: $BuildOutputDir"
    Write-Error-Custom "构建产物目录不存在"
    Write-Info "请先运行构建脚本: .\build.ps1"
} else {
    Write-Success "构建产物目录存在"
}

# ============================================
# 2. 验证 dist 目录
# ============================================
Write-Step "2/4: 验证 dist 目录"

$DistCheck = Test-DistDirectory -Path $DistDir

if (-not $DistCheck.Valid) {
    $Errors += "dist 目录验证失败: $($DistCheck.Message)"
    Write-Error-Custom "dist 目录验证失败: $($DistCheck.Message)"
} else {
    $TotalSizeMB = $DistCheck.TotalSize / 1MB
    Write-Success "dist 目录包含 $($DistCheck.FileCount) 个文件 ($([math]::Round($TotalSizeMB, 2)) MB)"
    
    # 检查文件数量是否合理
    if ($DistCheck.FileCount -lt 10) {
        $Warnings += "dist 目录文件数量较少 ($($DistCheck.FileCount) 个)，可能不完整"
        Write-Warning-Custom "文件数量较少，可能不完整"
    }
}

# ============================================
# 3. 验证 exe 文件
# ============================================
Write-Step "3/4: 验证 exe 文件"

# 检查是否是 onedir 模式
$OnedirPath = Join-Path $DistDir "Comfyui-Box"
if (Test-Path $OnedirPath) {
    # onedir 模式
    $ExePath = Join-Path $OnedirPath "Comfyui-Box.exe"
    $IsOnedir = $true
    Write-Info "检测到 onedir 模式"
} else {
    # onefile 模式
    $ExePath = Join-Path $DistDir "Comfyui-Box.exe"
    $IsOnedir = $false
    Write-Info "检测到 onefile 模式"
}

$ExeCheck = Test-ExeFile -Path $ExePath

if (-not $ExeCheck.Valid) {
    $Errors += "Comfyui-Box.exe 验证失败: $($ExeCheck.Message)"
    Write-Error-Custom "Comfyui-Box.exe 验证失败: $($ExeCheck.Message)"
} else {
    $ExeSizeMB = $ExeCheck.Size / 1MB
    Write-Success "Comfyui-Box.exe 存在 ($([math]::Round($ExeSizeMB, 2)) MB)"
    
    # 检查 exe 大小是否合理
    if ($ExeSizeMB -lt 1) {
        $Warnings += "exe 文件过小 ($([math]::Round($ExeSizeMB, 2)) MB)，可能不完整"
        Write-Warning-Custom "exe 文件可能不完整"
    } elseif ($ExeSizeMB -gt 100) {
        $Warnings += "exe 文件过大 ($([math]::Round($ExeSizeMB, 2)) MB)，可能包含不必要的文件"
        Write-Warning-Custom "exe 文件过大"
    }
    
    # onedir 模式：检查前端文件（在 _internal/dist 目录下）
    if ($IsOnedir) {
        $FrontendDistDir = Join-Path $OnedirPath "_internal\dist"
        if (Test-Path $FrontendDistDir) {
            $FrontendFiles = Get-ChildItem -Path $FrontendDistDir -Recurse -File
            Write-Success "前端文件目录存在，包含 $($FrontendFiles.Count) 个文件"
        } else {
            $Warnings += "前端文件目录不存在"
            Write-Warning-Custom "前端文件目录不存在"
        }
    }
}

# ============================================
# 4. 验证 ZIP 文件
# ============================================
Write-Step "4/4: 验证 ZIP 文件"

# 根据版本号生成 ZIP 文件名
if ($Version -like "RC*") {
    $ZipName = "Comfyui-Box-$Version-win64.zip"
} else {
    $ZipName = "Comfyui-Box-v$Version-win64.zip"
}
$ZipPath = Join-Path $BuildOutputDir $ZipName

if (-not (Test-Path $ZipPath)) {
    $Warnings += "ZIP 文件不存在: $ZipName"
    Write-Warning-Custom "ZIP 文件不存在: $ZipName"
    Write-Info "提示: 运行 .\create_release_package.ps1 -Version $Version 生成 ZIP 文件"
} else {
    $ZipCheck = Test-ZipFile -Path $ZipPath
    
    if (-not $ZipCheck.Valid) {
        $Errors += "ZIP 文件验证失败: $($ZipCheck.Message)"
        Write-Error-Custom "ZIP 文件验证失败: $($ZipCheck.Message)"
    } else {
        $ZipSizeMB = $ZipCheck.Size / 1MB
        Write-Success "ZIP 文件存在 ($([math]::Round($ZipSizeMB, 2)) MB)"
        Write-Success "ZIP 包含 $($ZipCheck.EntryCount) 个条目"
        
        # 验证 ZIP 内容
        try {
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $Zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
            
            # 检查 exe 文件
            if ($IsOnedir) {
                # onedir 模式
                $HasExe = $Zip.Entries | Where-Object { $_.FullName -like "Comfyui-Box/Comfyui-Box.exe" -or $_.FullName -like "Comfyui-Box\Comfyui-Box.exe" }
                if ($HasExe) {
                    Write-Success "✓ Comfyui-Box/Comfyui-Box.exe 已包含在 ZIP 中"
                } else {
                    $Errors += "ZIP 中缺少 Comfyui-Box/Comfyui-Box.exe"
                    Write-Error-Custom "ZIP 中缺少 Comfyui-Box/Comfyui-Box.exe"
                }
                
                # 检查前端文件（在 Comfyui-Box/_internal/dist/ 目录下）
                $HasDistFiles = $Zip.Entries | Where-Object { 
                    $_.FullName -like "Comfyui-Box/_internal/dist/*" -or 
                    $_.FullName -like "Comfyui-Box\_internal\dist\*" 
                }
                if ($HasDistFiles) {
                    $DistFileCount = ($HasDistFiles | Measure-Object).Count
                    Write-Success "✓ 前端文件已包含在 ZIP 中 ($DistFileCount 个文件)"
                } else {
                    $Warnings += "ZIP 中可能缺少前端文件"
                    Write-Warning-Custom "ZIP 中可能缺少前端文件"
                }
            } else {
                # onefile 模式
                $HasExe = $Zip.Entries | Where-Object { $_.Name -eq "Comfyui-Box.exe" }
                if ($HasExe) {
                    Write-Success "✓ Comfyui-Box.exe 已包含在 ZIP 中"
                } else {
                    $Errors += "ZIP 中缺少 Comfyui-Box.exe"
                    Write-Error-Custom "ZIP 中缺少 Comfyui-Box.exe"
                }
                
                # 检查前端文件
                $HasIndexHtml = $Zip.Entries | Where-Object { $_.Name -eq "index.html" }
                if ($HasIndexHtml) {
                    Write-Success "✓ 前端文件 (index.html) 已包含在 ZIP 中"
                } else {
                    $Warnings += "ZIP 中可能缺少前端文件"
                    Write-Warning-Custom "ZIP 中可能缺少前端文件"
                }
            }
            
            $Zip.Dispose()
            
        } catch {
            $Warnings += "无法验证 ZIP 内容: $_"
            Write-Warning-Custom "无法验证 ZIP 内容: $_"
        }
    }
}

# ============================================
# 5. 生成验证报告
# ============================================
Write-Host ""
Write-Step "验证结果"

if ($Errors.Count -eq 0 -and $Warnings.Count -eq 0) {
    Write-ColorOutput @"
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║                 ✓ 所有验证通过                            ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"@ "Green"
    Write-Host ""
    Write-Info "构建产物完整且有效"
    Write-Host ""
    exit 0
    
} elseif ($Errors.Count -eq 0) {
    Write-ColorOutput @"
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║            ⚠ 验证通过，但有警告                           ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"@ "Yellow"
    Write-Host ""
    Write-Host "警告列表:" -ForegroundColor Yellow
    foreach ($Warning in $Warnings) {
        Write-Host "  - $Warning" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Info "建议检查警告项，但可以继续使用"
    Write-Host ""
    exit 0
    
} else {
    Write-ColorOutput @"
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║                 ✗ 验证失败                                ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"@ "Red"
    Write-Host ""
    Write-Host "错误列表:" -ForegroundColor Red
    foreach ($Error in $Errors) {
        Write-Host "  - $Error" -ForegroundColor Red
    }
    
    if ($Warnings.Count -gt 0) {
        Write-Host ""
        Write-Host "警告列表:" -ForegroundColor Yellow
        foreach ($Warning in $Warnings) {
            Write-Host "  - $Warning" -ForegroundColor Yellow
        }
    }
    
    Write-Host ""
    Write-ColorOutput "建议操作:" "Yellow"
    Write-Host "  1. 重新运行完整构建: .\build.ps1"
    Write-Host "  2. 检查构建日志: $BuildOutputDir\build_report.txt"
    Write-Host "  3. 清理后重新构建: .\build.ps1"
    Write-Host ""
    
    exit 1
}
