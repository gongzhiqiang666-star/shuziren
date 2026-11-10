param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [string]$ReportDirectory = 'logs\validation\recovery-baseline'
)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$resolvedRuntime = (Resolve-Path -LiteralPath $RuntimeRoot).Path
$internal = if ((Split-Path -Leaf $resolvedRuntime) -eq '_internal') {
    $resolvedRuntime
} else { Join-Path $resolvedRuntime '_internal' }
$python = Join-Path $internal 'env\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Original CPython is missing: $python"
}
$reportRoot = if ([IO.Path]::IsPathRooted($ReportDirectory)) {
    $ReportDirectory
} else { Join-Path $workspace $ReportDirectory }
New-Item -ItemType Directory -Path $reportRoot -Force | Out-Null
$checks = @(
    @{ name='runtime-path-tests'; arguments=@('-I','-X','utf8','tests/test_recovery_runtime_paths.py') },
    @{ name='package-policy-tests'; arguments=@('-I','-X','utf8','tests/test_package_integrity_policy.py') },
    @{ name='function-matrix'; arguments=@('-I','-X','utf8','scripts/validate_function_matrix.py') },
    @{ name='recovery'; arguments=@('-I','-X','utf8','recovered/verify_recovery.py','--runtime-root',$internal) },
    @{ name='proof-tools'; arguments=@('-X','utf8','-m','unittest','scripts.test_v122_proof') }
)
$results = [System.Collections.Generic.List[object]]::new()
$oldPath = $env:PATH
$failed = $false
Push-Location -LiteralPath $workspace
try {
    $env:PATH = (Join-Path $internal 'env\ffmpeg\bin') + [IO.Path]::PathSeparator + $oldPath
    foreach ($check in $checks) {
        $log = Join-Path $reportRoot ($check.name + '.log')
        $started = Get-Date
        $arguments = $check.arguments
        & $python @arguments *> $log
        $code = $LASTEXITCODE
        $results.Add([ordered]@{
            name=$check.name; exit_code=$code; started_at=$started.ToString('o')
            elapsed_seconds=((Get-Date)-$started).TotalSeconds; log=$log
        })
        Write-Output ($check.name + ': exit ' + $code)
        if ($code -ne 0) { $failed = $true; break }
    }
} finally {
    $env:PATH = $oldPath
    $summary = [ordered]@{
        task='V00-02/V00-03'; source_commit=(& git rev-parse HEAD)
        source_changed_paths=@(& git diff --name-only HEAD) + @(& git ls-files --others --exclude-standard)
        runtime=$internal; generated_at=(Get-Date).ToString('o')
        status=$(if ($failed -or $results.Count -ne $checks.Count) {'failed'} else {'passed'})
        scope='Recovery contracts and software tools only; not live models/platform acceptance'
        checks=$results
    }
    $summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $reportRoot 'summary.json') -Encoding UTF8
    Pop-Location
}
if ($failed -or $results.Count -ne $checks.Count) { exit 1 }
