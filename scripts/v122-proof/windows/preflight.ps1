param([Parameter(Mandatory=$true)][string]$PackageRoot)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PackageRoot).Path
$runtime = Join-Path $root 'runtime\yunchuang_v122'
$python = Join-Path $runtime '_internal\env\python.exe'
$ffmpeg = Join-Path $runtime '_internal\env\ffmpeg\bin\ffmpeg.exe'
$ffprobe = Join-Path $runtime '_internal\env\ffmpeg\bin\ffprobe.exe'
$reportDir = Join-Path $root 'reports\preflight'
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$checks = [System.Collections.Generic.List[object]]::new()
function Add-Check([string]$Name,[string]$Status,[string]$Detail) { $checks.Add([ordered]@{name=$Name;status=$Status;detail=$Detail}) }
try {
  $drive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$([IO.Path]::GetPathRoot($root).TrimEnd('\'))'"
  $freeGB = [math]::Round($drive.FreeSpace / 1GB, 1)
  Add-Check 'disk' $(if($freeGB -ge 30){'pass'}else{'blocked'}) "$freeGB GB freeSpace"
} catch { Add-Check 'disk' 'blocked' 'FreeSpace unavailable' }
if (Test-Path -LiteralPath $python) { Add-Check 'python' 'pass' 'bundled env' } else { Add-Check 'python' 'blocked' 'python.exe missing' }
if ((Test-Path -LiteralPath $ffmpeg) -and (Test-Path -LiteralPath $ffprobe)) { Add-Check 'media' 'pass' 'ffmpeg.exe and ffprobe.exe' } else { Add-Check 'media' 'blocked' 'media tools missing' }
try { $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>&1 | Select-Object -First 1); if($LASTEXITCODE){throw 'nvidia-smi failed'}; Add-Check 'nvidia-smi' 'pass' ([string]$gpu) } catch { Add-Check 'nvidia-smi' 'blocked' 'NVIDIA driver unavailable' }
if (Test-Path -LiteralPath $python) {
  $cuda = & $python -c "import torch; print(torch.cuda.is_available())" 2>&1
  Add-Check 'torch-cuda' $(if($LASTEXITCODE -eq 0 -and "$cuda" -match 'True'){'pass'}else{'blocked'}) "torch.cuda.is_available=$cuda"
  $onnx = & $python -c "import onnxruntime as o; print(','.join(o.get_available_providers()))" 2>&1
  Add-Check 'onnxruntime' $(if($LASTEXITCODE -eq 0 -and "$onnx" -match 'CUDAExecutionProvider'){'pass'}else{'blocked'}) ([string]$onnx)
  $verify = Join-Path $root 'proof\scripts\verify_v122_package.py'
  $integrity = Join-Path $reportDir 'package-integrity.json'
  & $python $verify --root $root --output $integrity | Out-Null
  Add-Check 'package' $(if($LASTEXITCODE -eq 0){'pass'}else{'blocked'}) 'package-integrity.json'
}
$result = [ordered]@{ generated_at=(Get-Date).ToString('o'); checks=$checks; blocked=@($checks | Where-Object status -eq 'blocked').Count -gt 0 }
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $reportDir 'environment.json') -Encoding UTF8
$result | ConvertTo-Json -Depth 5
if ($result.blocked) { exit 1 }
