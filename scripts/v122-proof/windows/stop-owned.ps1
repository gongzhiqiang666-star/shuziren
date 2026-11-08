param([Parameter(Mandatory=$true)][string]$PackageRoot)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PackageRoot).Path
$state = Join-Path $root 'runs\tool-process.json'
if (!(Test-Path -LiteralPath $state)) { Write-Host '本工具没有正在登记的进程。'; exit 0 }
$owned = Get-Content -LiteralPath $state -Raw -Encoding UTF8 | ConvertFrom-Json
$actual = Get-CimInstance Win32_Process -Filter "ProcessId=$($owned.pid)" -ErrorAction SilentlyContinue
if ($null -eq $actual) { Remove-Item -LiteralPath $state; exit 0 }
if ($actual.ExecutablePath -ne $owned.executable -or $actual.CreationDate -ne $owned.created) { throw 'PID已被其他进程复用，拒绝停止' }
Stop-Process -Id $owned.pid
Remove-Item -LiteralPath $state
Write-Host '已停止本工具启动的本地服务。'
