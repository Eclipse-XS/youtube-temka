param([ValidateSet('controller','worker')][string]$Role='controller')
$ErrorActionPreference='Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$envFile=Join-Path (Get-Location) '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath '.env.example' -Destination $envFile
}
$text=Get-Content -LiteralPath $envFile -Raw
if ($text -notmatch '(?m)^FACTORY_TOKEN=.{32,}$') {
    $bytes=New-Object byte[] 36
    $rng=[System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    $secret=[Convert]::ToBase64String($bytes)
    if ($text -match '(?m)^FACTORY_TOKEN=.*$') {
        $text=[regex]::Replace($text,'(?m)^FACTORY_TOKEN=.*$',"FACTORY_TOKEN=$secret")
    } else {
        $text += "`nFACTORY_TOKEN=$secret`n"
    }
    [System.IO.File]::WriteAllText($envFile,$text,(New-Object System.Text.UTF8Encoding($false)))
}
New-Item -ItemType Directory -Force -Path 'secrets' | Out-Null
Write-Host 'Configuration preserved. Controller token is in .env; OAuth files are not modified.'
if ($Role -eq 'worker') {
    Write-Host 'Set CONTROLLER_URL to PC A private/Tailscale URL and FACTORY_TOKEN to its existing token in .env.'
    Write-Host 'Give this worker its own authorized Google token files. Do not assume copied refresh credentials are valid.'
}
Write-Host "Start: docker compose --profile $Role up -d --build"
