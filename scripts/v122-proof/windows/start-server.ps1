param([Parameter(Mandatory=$true)][string]$PackageRoot)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PackageRoot).Path
$python = Join-Path $root 'runtime\yunchuang_v122\_internal\env\python.exe'
$server = Join-Path $root 'proof\scripts\v122_proof_server.py'
$web = Join-Path $root 'proof\web'
$state = Join-Path $root 'runs\tool-process.json'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $server)) { throw '验证运行环境不完整' }
New-Item -ItemType Directory -Force -Path (Split-Path $state) | Out-Null
$process = Start-Process -FilePath $python -ArgumentList @($server,'--root',$root,'--web',$web,'--port','5157') -WorkingDirectory $root -PassThru -WindowStyle Hidden
$details = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
@{ pid=$process.Id; executable=$python; created=$details.CreationDate } | ConvertTo-Json | Set-Content -LiteralPath $state -Encoding UTF8
for ($i=0; $i -lt 40; $i++) { try { Invoke-RestMethod -Uri 'http://127.0.0.1:5157/api/state' -TimeoutSec 1 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 250 } }
throw '本地验证网页启动超时，请查看日志'
