# AIVP environment check
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$failed = $false

function Assert-Cmd([string]$Name, [switch]$Optional) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "OK  $Name: $($cmd.Source)" -ForegroundColor Green
    } elseif ($Optional) {
        Write-Host "WARN  $Name not found (optional)" -ForegroundColor DarkYellow
    } else {
        Write-Host "MISSING  $Name" -ForegroundColor Red
        $script:failed = $true
    }
}

Assert-Cmd python
Assert-Cmd npm
Assert-Cmd node

try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) {
        Write-Host "OK  ollama: http://127.0.0.1:11434" -ForegroundColor Green
    }
} catch {
    Write-Host "WARN  ollama not reachable (optional for text extract)" -ForegroundColor DarkYellow
}

if (-not (Test-Path (Join-Path $Root "backend\pyproject.toml"))) {
    Write-Host "MISSING  backend/pyproject.toml" -ForegroundColor Red
    $failed = $true
}
if (-not (Test-Path (Join-Path $Root "frontend\package.json"))) {
    Write-Host "MISSING  frontend/package.json" -ForegroundColor Red
    $failed = $true
}

if ($failed) { exit 1 }
Write-Host "Environment check passed." -ForegroundColor Cyan
