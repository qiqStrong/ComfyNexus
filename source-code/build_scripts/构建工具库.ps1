# ComfyNexus 构建工具函数库
# 用途: 提供可复用的构建工具函数
# 版本: 1.0.0

# ============================================
# 颜色输出函数
# ============================================

function Write-ColorOutput {
    <#
    .SYNOPSIS
    输出带颜色的文本
    
    .PARAMETER Message
    要输出的消息
    
    .PARAMETER Color
    文本颜色
    #>
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Step {
    <#
    .SYNOPSIS
    输出步骤标题
    
    .PARAMETER Message
    步骤标题
    #>
    param([string]$Message)
    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput $Message "Cyan"
    Write-ColorOutput "========================================`n" "Cyan"
}

function Write-Success {
    <#
    .SYNOPSIS
    输出成功消息
    
    .PARAMETER Message
    成功消息
    #>
    param([string]$Message)
    Write-ColorOutput "✓ $Message" "Green"
}

function Write-Error-Custom {
    <#
    .SYNOPSIS
    输出错误消息
    
    .PARAMETER Message
    错误消息
    #>
    param([string]$Message)
    Write-ColorOutput "✗ $Message" "Red"
}

function Write-Warning-Custom {
    <#
    .SYNOPSIS
    输出警告消息
    
    .PARAMETER Message
    警告消息
    #>
    param([string]$Message)
    Write-ColorOutput "⚠ $Message" "Yellow"
}

function Write-Info {
    <#
    .SYNOPSIS
    输出信息消息
    
    .PARAMETER Message
    信息消息
    #>
    param([string]$Message)
    Write-ColorOutput "ℹ $Message" "Blue"
}

# ============================================
# 版本处理函数
# ============================================

function Get-ProjectVersion {
    <#
    .SYNOPSIS
    从 comfy_nexus_version.py 文件读取项目版本号
    
    .DESCRIPTION
    读取项目根目录的 comfy_nexus_version.py 文件，解析 __version__ 变量
    
    .OUTPUTS
    System.String
    版本号字符串
    
    .EXAMPLE
    $version = Get-ProjectVersion
    #>
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
    $VersionFile = Join-Path $ProjectRoot "comfy_nexus_version.py"
    if (Test-Path $VersionFile) {
        $content = Get-Content $VersionFile -Raw
        if ($content -match '__version__\s*=\s*[\"'']([^\"'']*)[\"'']') {
            return $matches[1]
        }
    }
    return "V1.0.0"
}

# ============================================
# 验证函数
# ============================================

function Test-DistDirectory {
    <#
    .SYNOPSIS
    验证 dist 目录的有效性
    
    .PARAMETER Path
    dist 目录路径
    
    .OUTPUTS
    System.Collections.Hashtable
    包含验证结果的哈希表
    
    .EXAMPLE
    $result = Test-DistDirectory -Path ".\dist"
    if ($result.Valid) {
        Write-Host "目录有效，包含 $($result.FileCount) 个文件"
    }
    #>
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        return @{
            Valid = $false
            Message = "目录不存在"
        }
    }
    
    $Files = Get-ChildItem -Path $Path -Recurse -File
    if ($Files.Count -eq 0) {
        return @{
            Valid = $false
            Message = "目录为空"
        }
    }
    
    return @{
        Valid = $true
        FileCount = $Files.Count
        TotalSize = ($Files | Measure-Object -Property Length -Sum).Sum
    }
}

function Test-ExeFile {
    <#
    .SYNOPSIS
    验证 exe 文件的有效性
    
    .PARAMETER Path
    exe 文件路径
    
    .OUTPUTS
    System.Collections.Hashtable
    包含验证结果的哈希表
    
    .EXAMPLE
    $result = Test-ExeFile -Path ".\dist\ComfyNexus.exe"
    if ($result.Valid) {
        Write-Host "exe 文件有效，大小: $($result.Size) 字节"
    }
    #>
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        return @{
            Valid = $false
            Message = "文件不存在"
        }
    }
    
    $Size = (Get-Item $Path).Length
    if ($Size -eq 0) {
        return @{
            Valid = $false
            Message = "文件大小为 0"
        }
    }
    
    return @{
        Valid = $true
        Size = $Size
    }
}

function Test-ZipFile {
    <#
    .SYNOPSIS
    验证 ZIP 文件的有效性
    
    .PARAMETER Path
    ZIP 文件路径
    
    .OUTPUTS
    System.Collections.Hashtable
    包含验证结果的哈希表
    
    .EXAMPLE
    $result = Test-ZipFile -Path ".\ComfyNexus-v1.0.0-win64.zip"
    if ($result.Valid) {
        Write-Host "ZIP 文件有效，包含 $($result.EntryCount) 个条目"
    }
    #>
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        return @{
            Valid = $false
            Message = "文件不存在"
        }
    }
    
    $Size = (Get-Item $Path).Length
    if ($Size -eq 0) {
        return @{
            Valid = $false
            Message = "文件大小为 0"
        }
    }
    
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $Zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
        $EntryCount = $Zip.Entries.Count
        $Zip.Dispose()
        
        return @{
            Valid = $true
            Size = $Size
            EntryCount = $EntryCount
        }
    } catch {
        return @{
            Valid = $false
            Message = "无法读取 ZIP 文件: $_"
        }
    }
}

# ============================================
# 文件操作函数
# ============================================

function Get-FileSize {
    <#
    .SYNOPSIS
    获取文件大小
    
    .PARAMETER Path
    文件路径
    
    .OUTPUTS
    System.Int64
    文件大小（字节）
    
    .EXAMPLE
    $size = Get-FileSize -Path ".\dist\ComfyNexus.exe"
    #>
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        return 0
    }
    
    return (Get-Item $Path).Length
}

function Get-DirectorySize {
    <#
    .SYNOPSIS
    获取目录大小（递归）
    
    .PARAMETER Path
    目录路径
    
    .OUTPUTS
    System.Int64
    目录大小（字节）
    
    .EXAMPLE
    $size = Get-DirectorySize -Path ".\dist"
    #>
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        return 0
    }
    
    $Files = Get-ChildItem -Path $Path -Recurse -File
    return ($Files | Measure-Object -Property Length -Sum).Sum
}

# ============================================
# 发布包生成函数
# ============================================

function New-ReleasePackage {
    <#
    .SYNOPSIS
    创建发布包（ZIP 文件）
    
    .DESCRIPTION
    从 dist 目录创建发布包，包含完整的验证和错误处理
    
    .PARAMETER DistDir
    dist 目录路径
    
    .PARAMETER Version
    版本号
    
    .PARAMETER OutputDir
    输出目录路径（产物目录）
    
    .PARAMETER VerboseOutput
    是否输出详细信息
    
    .OUTPUTS
    System.Collections.Hashtable
    包含生成结果的哈希表
    
    .EXAMPLE
    $result = New-ReleasePackage -DistDir ".\dist" -Version "1.0.0" -OutputDir ".\build_scripts\打包产物_1.0.0" -VerboseOutput
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$DistDir,
        
        [Parameter(Mandatory=$true)]
        [string]$Version,
        
        [Parameter(Mandatory=$true)]
        [string]$OutputDir,
        
        [Parameter(Mandatory=$false)]
        [switch]$VerboseOutput
    )
    
    Write-Step "创建发布包"
    
    # 获取项目根目录
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
    
    # 确保输出目录存在
    if (-not (Test-Path $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
        Write-Info "创建输出目录: $OutputDir"
    }
    
    # 1. 验证 dist 目录
    Write-Info "验证 dist 目录..."
    $DistCheck = Test-DistDirectory -Path $DistDir
    
    if (-not $DistCheck.Valid) {
        throw "dist 目录验证失败: $($DistCheck.Message)"
    }
    
    $TotalSizeMB = $DistCheck.TotalSize / 1MB
    Write-Success "dist 目录包含 $($DistCheck.FileCount) 个文件 ($([math]::Round($TotalSizeMB, 2)) MB)"
    
    # 2. 验证关键文件（支持 onedir 模式）
    Write-Info "验证关键文件..."
    
    # 检查是否是 onedir 模式（有 ComfyNexus 子目录）
    $OnedirPath = Join-Path $DistDir "ComfyNexus"
    if (Test-Path $OnedirPath) {
        # onedir 模式
        $ExePath = Join-Path $OnedirPath "ComfyNexus.exe"
        $IsOnedir = $true
        Write-Info "检测到 onedir 模式"
    } else {
        # onefile 模式
        $ExePath = Join-Path $DistDir "ComfyNexus.exe"
        $IsOnedir = $false
        Write-Info "检测到 onefile 模式"
    }
    
    $ExeCheck = Test-ExeFile -Path $ExePath
    
    if (-not $ExeCheck.Valid) {
        throw "ComfyNexus.exe 验证失败: $($ExeCheck.Message)"
    }
    
    $ExeSizeMB = $ExeCheck.Size / 1MB
    Write-Success "ComfyNexus.exe 存在 ($([math]::Round($ExeSizeMB, 2)) MB)"
    
    # 3. 生成 ZIP 文件名
    # 先去掉 v 前缀（如果有），避免出现 vv1.0.2
    $CleanVersion = $Version
    if ($CleanVersion -like "v*") {
        $CleanVersion = $CleanVersion.Substring(1)
    }
    
    # 如果版本号以 RC 开头，则不添加 v 前缀
    if ($CleanVersion -like "RC*") {
        $ZipName = "ComfyNexus-$CleanVersion-win64.zip"
    } else {
        $ZipName = "ComfyNexus-v$CleanVersion-win64.zip"
    }
    $ZipPath = Join-Path $OutputDir $ZipName
    
    Write-Info "目标文件: $ZipName"
    
    # 4. 删除旧的压缩包
    if (Test-Path $ZipPath) {
        Write-Info "删除旧的压缩包..."
        try {
            Remove-Item $ZipPath -Force -ErrorAction Stop
            Write-Success "旧压缩包已删除"
        } catch {
            Write-Warning-Custom "无法删除旧压缩包: $_"
            Write-Info "尝试使用新文件名..."
            $Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
            if ($CleanVersion -like "RC*") {
                $ZipName = "ComfyNexus-$CleanVersion-win64-$Timestamp.zip"
            } else {
                $ZipName = "ComfyNexus-v$CleanVersion-win64-$Timestamp.zip"
            }
            $ZipPath = Join-Path $OutputDir $ZipName
            Write-Info "新文件名: $ZipName"
        }
    }
    
    # 5. 创建压缩包
    Write-Info "创建压缩包..."
    try {
        # 根据模式选择压缩路径
        if ($IsOnedir) {
            # onedir 模式：压缩整个 ComfyNexus 目录
            $CompressPath = Join-Path $DistDir "ComfyNexus"
        } else {
            # onefile 模式：压缩所有文件
            $CompressPath = "$DistDir\*"
        }
        
        $CompressParams = @{
            Path = $CompressPath
            DestinationPath = $ZipPath
            CompressionLevel = 'Optimal'
            Force = $true
            ErrorAction = 'Stop'
        }
        
        Compress-Archive @CompressParams
        Write-Success "压缩包创建成功"
        
    } catch {
        Write-Error-Custom "压缩包创建失败"
        Write-Error-Custom "错误详情: $_"
        
        # 提供解决方案
        Write-Host ""
        Write-Warning-Custom "可能的原因和解决方案:"
        Write-Host "  1. 磁盘空间不足 - 请检查磁盘空间" -ForegroundColor Yellow
        Write-Host "  2. 文件被占用 - 请关闭可能占用文件的程序" -ForegroundColor Yellow
        Write-Host "  3. 权限不足 - 请以管理员身份运行" -ForegroundColor Yellow
        Write-Host "  4. 路径过长 - 请将项目移到较短的路径" -ForegroundColor Yellow
        Write-Host ""
        
        throw
    }
    
    # 6. 验证 ZIP 文件
    Write-Info "验证 ZIP 文件..."
    $ZipCheck = Test-ZipFile -Path $ZipPath
    
    if (-not $ZipCheck.Valid) {
        # 删除无效的 ZIP 文件
        if (Test-Path $ZipPath) {
            Remove-Item $ZipPath -Force
        }
        throw "ZIP 文件验证失败: $($ZipCheck.Message)"
    }
    
    $ZipSizeMB = $ZipCheck.Size / 1MB
    Write-Success "ZIP 文件大小: $([math]::Round($ZipSizeMB, 2)) MB"
    
    # 7. 验证 ZIP 内容（详细模式）
    if ($VerboseOutput) {
        Write-Info "验证 ZIP 内容..."
        try {
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $Zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
            $EntryCount = $Zip.Entries.Count
            
            Write-Success "ZIP 包含 $EntryCount 个条目"
            
            # 检查关键文件
            if ($IsOnedir) {
                # onedir 模式：检查 ComfyNexus/ComfyNexus.exe
                $HasExe = $Zip.Entries | Where-Object { $_.FullName -like "ComfyNexus/ComfyNexus.exe" -or $_.FullName -like "ComfyNexus\ComfyNexus.exe" }
                if ($HasExe) {
                    Write-Success "✓ ComfyNexus/ComfyNexus.exe 已包含"
                } else {
                    Write-Warning-Custom "✗ ComfyNexus/ComfyNexus.exe 未找到"
                }
                
                # 检查前端文件（在 ComfyNexus/_internal/dist/ 目录下）
                $HasDistFiles = $Zip.Entries | Where-Object { 
                    $_.FullName -like "ComfyNexus/_internal/dist/*" -or 
                    $_.FullName -like "ComfyNexus\_internal\dist\*" 
                }
                if ($HasDistFiles) {
                    $DistFileCount = ($HasDistFiles | Measure-Object).Count
                    Write-Success "✓ 前端文件已包含 ($DistFileCount 个文件)"
                } else {
                    Write-Warning-Custom "✗ 前端文件未找到"
                }
            } else {
                # onefile 模式：检查 ComfyNexus.exe
                $HasExe = $Zip.Entries | Where-Object { $_.Name -eq "ComfyNexus.exe" }
                if ($HasExe) {
                    Write-Success "✓ ComfyNexus.exe 已包含"
                } else {
                    Write-Warning-Custom "✗ ComfyNexus.exe 未找到"
                }
                
                # 检查前端文件（在根目录）
                $HasIndexHtml = $Zip.Entries | Where-Object { $_.Name -eq "index.html" }
                if ($HasIndexHtml) {
                    Write-Success "✓ 前端文件 (index.html) 已包含"
                } else {
                    Write-Warning-Custom "✗ 前端文件未找到"
                }
            }
            
            $Zip.Dispose()
            
        } catch {
            Write-Warning-Custom "无法验证 ZIP 内容: $_"
        }
    }
    
    # 8. 返回结果
    return @{
        Success = $true
        ZipPath = $ZipPath
        ZipName = $ZipName
        ZipSize = $ZipSizeMB
        FileCount = $DistCheck.FileCount
        EntryCount = $ZipCheck.EntryCount
    }
}
