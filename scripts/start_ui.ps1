param(
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Load non-empty values from the project .env without printing secrets.
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $key = $parts[0].Trim()
            $value = $parts[1].Trim()
            if ($key -and $value -and (-not (Test-Path "Env:$key") -or -not (Get-Item "Env:$key").Value)) {
                Set-Item "Env:$key" $value
            }
        }
    }
}

if (-not $env:REFLEX_API_SECRET) {
    throw "REFLEX_API_SECRET is not configured. Copy .env.example to .env and set a secret."
}

$env:REFLEX_UI_PORT = "$Port"
Write-Host "Starting DataHub Reflex UI on http://127.0.0.1:$Port"
python -m ui.app
