# Comfyui-Box 构建脚本入口
# 用途: 从项目根目录调用构建脚本
# 使用方法: .\build.ps1 [-Version "1.0.2"] [-SkipFrontend] [-SkipClean] [-SkipTests] [-VerboseOutput]

param(
    [Parameter(Mandatory=$false)]
    [string]$Version = "",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipFrontend = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipClean = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipTests = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$VerboseOutput = $false
)

# 构建参数数组
$params = @{}
if ($Version) { $params['Version'] = $Version }
if ($SkipFrontend) { $params['SkipFrontend'] = $true }
if ($SkipClean) { $params['SkipClean'] = $true }
if ($SkipTests) { $params['SkipTests'] = $true }
if ($VerboseOutput) { $params['VerboseOutput'] = $true }

# 调用 build_scripts 目录下的构建脚本
& "$PSScriptRoot\build_scripts\构建.ps1" @params
