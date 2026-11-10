$ErrorActionPreference = 'Stop'
$noSample = $false
$prepareOnly = $false
foreach ($argument in $args) {
    switch ($argument) {
        '--no-sample' { $noSample = $true }
        '-NoSample' { $noSample = $true }
        '--prepare-only' { $prepareOnly = $true }
        '-PrepareOnly' { $prepareOnly = $true }
        { $_ -in @('--help', '-h', '-Help') } {
            Write-Host '用法：powershell -File scripts/start-avatar3d.ps1 [--no-sample] [--prepare-only]'
            Write-Host '--no-sample：跳过内置人物下载，在页面导入自己的 GLB。'
            Write-Host '--prepare-only：只准备资源和前端依赖，不启动浏览器。'
            exit 0
        }
        default { throw "不支持的参数：$argument" }
    }
}

$projectDir = Split-Path -Parent $PSScriptRoot
Set-Location $projectDir
$nodeCommand = Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
# Prefer npm.cmd so a blocked npm.ps1 does not prevent local development.
$npmCommand = Get-Command npm.cmd -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $npmCommand) {
    $npmCommand = Get-Command npm -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $nodeCommand) { throw '请先安装 Node.js（建议使用 Node.js 24）。' }
if (-not $npmCommand) { throw '未找到 npm，请检查 Node.js 安装。' }
& $nodeCommand.Source -e 'const [m,n]=process.versions.node.match(/[0-9]+/g).map(Number); if (!((m===20&&n>=19)||(m===22&&n>=12)||m>=24)) process.exit(1)'
if ($LASTEXITCODE -ne 0) { throw 'Node.js 版本不符合要求，请使用 Node.js 24，或 20.19+/22.12+。' }
& $npmCommand.Source --version
if ($LASTEXITCODE -ne 0) { throw 'npm 无法正常运行，请修复 Node.js 安装。' }

$pythonExecutable = $null
$pythonPrefix = @()
$candidates = @(
    @{ Name = 'py'; Prefix = @('-3') },
    @{ Name = 'python3'; Prefix = @() },
    @{ Name = 'python'; Prefix = @() }
)
foreach ($candidate in $candidates) {
    $command = Get-Command $candidate.Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) { continue }
    $probeArguments = @($candidate.Prefix) + @('-c', 'import sys; print(sys.version_info.major); sys.exit(0 if sys.version_info >= (3,10) else 1)')
    try {
        $probeOutput = & $command.Source @probeArguments 2>$null
        if ($LASTEXITCODE -eq 0 -and ($probeOutput -join "`n").Trim() -eq '3') {
            $pythonExecutable = $command.Source
            $pythonPrefix = @($candidate.Prefix)
            break
        }
    } catch {
        # Keep probing: Windows may expose a launcher or Store alias without a working Python.
    }
}
if (-not $pythonExecutable) { throw '未找到可运行的 Python 3.10+。请安装 Python 3 并重新打开终端。' }
$setupArguments = $pythonPrefix + @((Join-Path $projectDir 'scripts/avatar3d_setup.py'))
if ($noSample) { $setupArguments += '--no-sample' }
& $pythonExecutable @setupArguments
if ($LASTEXITCODE -ne 0) { throw '样例准备未完成。可使用 --no-sample 跳过样例，再在页面导入自己的 GLB。' }

Set-Location (Join-Path $projectDir 'web')
Write-Host '安装锁定的前端依赖（首次准备需要联网）。'
& $npmCommand.Source ci
if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败。请检查网络和 Node.js 版本后重试。' }
if ($prepareOnly) {
    Write-Host '准备完成。需要启动时，在 web 目录运行 npm run avatar3d。'
    exit 0
}
Write-Host '启动本地 3D 页：http://127.0.0.1:5173/avatar3d'
Write-Host '关闭本终端或按 Ctrl+C 停止。此命令不会开直播或调用付费接口。'
& $npmCommand.Source run avatar3d
if ($LASTEXITCODE -ne 0) { throw '3D 页面未正常启动。请检查上方错误信息及 5173 端口占用。' }
