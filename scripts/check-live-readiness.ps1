[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Manifest,
    [string]$Output = "test-results/live-readiness/windows-preflight.json"
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$manifestPath = (Resolve-Path -LiteralPath $Manifest).Path
$config = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$checks = [System.Collections.Generic.List[object]]::new()

function Add-Check([string]$Name, [string]$Status, [bool]$Required, [string]$Detail) {
    $checks.Add([ordered]@{ name = $Name; status = $Status; required = $Required; detail = $Detail })
}

try {
    $os = Get-CimInstance Win32_OperatingSystem
    Add-Check 'windows' 'pass' $true ($os.Caption + ' ' + $os.Version)
    Add-Check 'memory' 'pass' $true ([math]::Round($os.TotalVisibleMemorySize / 1MB, 1).ToString() + ' GiB')
} catch { Add-Check 'windows' 'unverified' $true 'Win32_OperatingSystem unavailable' }

$gpuText = & nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>$null
if ($LASTEXITCODE -eq 0 -and $gpuText) { Add-Check 'nvidia_gpu' 'pass' $true ($gpuText -join '; ') }
else { Add-Check 'nvidia_gpu' 'fail' $true 'nvidia-smi unavailable' }

try {
    $sound = @(Get-CimInstance Win32_SoundDevice | Where-Object Status -eq 'OK')
    Add-Check 'audio_devices' $(if ($sound.Count) { 'pass' } else { 'fail' }) $true ($sound.Count.ToString() + ' ready device(s)')
} catch { Add-Check 'audio_devices' 'unverified' $true 'Win32_SoundDevice unavailable' }

$obsCandidates = @(
    "$env:ProgramFiles\obs-studio\bin\64bit\obs64.exe",
    "${env:ProgramFiles(x86)}\obs-studio\bin\64bit\obs64.exe"
)
Add-Check 'obs' $(if ($obsCandidates | Where-Object { Test-Path -LiteralPath $_ }) { 'pass' } else { 'fail' }) $true 'obs64.exe'

$runtimeRoot = [string]$config.runtime.root
$srs = Join-Path $runtimeRoot 'assets\srs\srs-live.bat'
$camera64 = Join-Path $runtimeRoot 'assets\plugin\camera\obs-virtualcam-module64.dll'
$camera32 = Join-Path $runtimeRoot 'assets\plugin\camera\obs-virtualcam-module32.dll'
Add-Check 'srs' $(if (Test-Path -LiteralPath $srs) { 'pass' } else { 'fail' }) ($config.output.mode -eq 'srs') 'srs-live.bat'
Add-Check 'virtual_camera_dlls' $(if ((Test-Path -LiteralPath $camera64) -and (Test-Path -LiteralPath $camera32)) { 'pass' } else { 'fail' }) ($config.output.mode -eq 'virtual_camera') 'obs-virtualcam-module64.dll and 32-bit peer'

$webView = Test-Path 'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\*' -ErrorAction SilentlyContinue
Add-Check 'webview2' $(if ($webView) { 'pass' } else { 'unverified' }) $false 'WebView2 registry presence'

foreach ($port in @(8010, 9880, 1935)) {
    try {
        $listener = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop)
        Add-Check ("port_" + $port) $(if ($listener.Count) { 'pass' } else { 'unverified' }) $false 'listener state only'
    } catch { Add-Check ("port_" + $port) 'unverified' $false 'Get-NetTCPConnection unavailable or no listener' }
}

$assetOutput = Join-Path (Split-Path -Parent ([IO.Path]::GetFullPath($Output))) 'assets.json'
$validator = Join-Path $PSScriptRoot 'live_readiness.py'
$python = [string]$config.runtime.python
if (Test-Path -LiteralPath $python) {
    & $python $validator check-assets --manifest $manifestPath --output $assetOutput
} else {
    & py -3.11 $validator check-assets --manifest $manifestPath --output $assetOutput
}
$assetExit = $LASTEXITCODE
Add-Check 'asset_manifest' $(if ($assetExit -eq 0) { 'pass' } else { 'fail' }) $true 'check-assets'

$ready = -not ($checks | Where-Object { $_.required -and $_.status -ne 'pass' })
$report = [ordered]@{
    schema = 1
    ready = $ready
    checks = $checks
    not_measured = @('model quality', 'lip sync', 'OBS audio/video content', 'platform delivery', 'stability')
}
$outputPath = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $outputPath) | Out-Null
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $outputPath -Encoding UTF8
$checks | ForEach-Object { Write-Host ($_.status.ToUpper() + ' ' + $_.name + ' - ' + $_.detail) }
Write-Host ('Report: ' + $outputPath)
if ($ready) { exit 0 } else { exit 1 }
