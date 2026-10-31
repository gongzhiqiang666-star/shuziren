$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
Set-Location $projectDir
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Please install Docker Desktop with Compose first.' }
& docker compose version
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is unavailable.' }
if (-not (Test-Path '.env')) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $bytes = New-Object byte[] 32
        $rng.GetBytes($bytes)
        $appSecret = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
        $rng.GetBytes($bytes)
        $databaseSecret = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
        $content = [IO.File]::ReadAllText((Join-Path $projectDir '.env.example'))
        $content = [regex]::Replace($content, '(?m)^APP_TOKEN=\r?$', ('APP_TOKEN=' + $appSecret))
        $content = [regex]::Replace($content, '(?m)^POSTGRES_PASSWORD=\r?$', ('POSTGRES_PASSWORD=' + $databaseSecret))
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        $stream = [IO.File]::Open((Join-Path $projectDir '.env'), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $encoded = $utf8.GetBytes($content); $stream.Write($encoded, 0, $encoded.Length) } finally { $stream.Dispose() }
    } finally { $rng.Dispose() }
}
& docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration is invalid. Review .env without sharing its secrets.' }
& docker compose up --build -d --wait --wait-timeout 180
if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Run docker compose logs app to inspect the service.' }
Write-Host 'Workspace: http://127.0.0.1:8765 (or APP_PORT in .env)'
Write-Host 'The workspace access token is APP_TOKEN in .env. Keep this file private.'
Write-Host 'This starts the workspace and PostgreSQL. Configure TTS and LiveTalking separately.'
