param([Parameter(Mandatory=$true)][string]$PackageRoot)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PackageRoot).Path
$python = Join-Path $root 'runtime\yunchuang_v122\_internal\env\python.exe'
$server = Join-Path $root 'proof\scripts\v122_proof_server.py'
$web = Join-Path $root 'proof\web'
$state = Join-Path $root 'runs\tool-process.json'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $server)) { throw '验证运行环境不完整' }
& (Join-Path $root 'proof\windows\preflight.ps1') -PackageRoot $root | Out-Host
if ($LASTEXITCODE -ne 0) { throw '环境或离线包完整性检查未通过，请查看 reports\preflight' }
New-Item -ItemType Directory -Force -Path (Split-Path $state) | Out-Null
function Quote-Argument([string]$Value) {
  if ($Value.Contains('"')) { throw '启动参数不能包含双引号' }
  return '"' + $Value + '"'
}
$arguments = @($server,'--root',$root,'--web',$web,'--port','5157') | ForEach-Object { Quote-Argument $_ }
$process = Start-Process -FilePath $python -ArgumentList ($arguments -join ' ') -WorkingDirectory $root -PassThru -WindowStyle Hidden
$details = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
@{ pid=$process.Id; executable=$python; created=$details.CreationDate } | ConvertTo-Json | Set-Content -LiteralPath $state -Encoding UTF8
for ($i=0; $i -lt 40; $i++) { try { Invoke-RestMethod -Uri 'http://127.0.0.1:5157/api/state' -TimeoutSec 1 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 250 } }
throw '本地验证网页启动超时，请查看日志'
