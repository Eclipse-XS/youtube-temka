# Isolated first-run/config-preservation checks; no real Docker calls.
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('factory-launcher-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $temporary 'scripts') -Force | Out-Null
Copy-Item -LiteralPath "$repo/scripts/start-factory.ps1" -Destination "$temporary/scripts/start-factory.ps1"
Copy-Item -LiteralPath "$repo/.env.example" -Destination "$temporary/.env.example"
function docker {
    $global:LASTEXITCODE=0
    if ($args[0] -eq 'info') {
        if ($args -contains '--format') { 'linux' }
        return
    }
    $global:LASTEXITCODE=17 # Stop before any mutation; config is intentionally unavailable.
}
function wsl { $global:LASTEXITCODE=0 }
& "$temporary/scripts/start-factory.ps1" -CpuOnly *> (Join-Path $temporary 'first-run.log')
if ($LASTEXITCODE -ne 1) { throw 'Expected deployment failure from simulated Compose configuration.' }
$envPath=Join-Path $temporary '.env'
$created=[IO.File]::ReadAllText($envPath)
if ($created -notmatch '(?m)^FACTORY_TOKEN=([A-Za-z0-9+/=]{64})\r?$') { throw 'First run did not generate a secure local token.' }
& "$temporary/scripts/start-factory.ps1" -CpuOnly *> (Join-Path $temporary 'repeat.log')
if ([IO.File]::ReadAllText($envPath) -ne $created) { throw 'Existing configuration was overwritten.' }
[IO.File]::WriteAllText($envPath,"FACTORY_TOKEN=invalid`nKEEP_ME=yes`n")
$invalid=[IO.File]::ReadAllText($envPath)
& "$temporary/scripts/start-factory.ps1" -CpuOnly *> (Join-Path $temporary 'invalid.log')
if ($LASTEXITCODE -ne 1 -or [IO.File]::ReadAllText($envPath) -ne $invalid) { throw 'Invalid existing configuration was not preserved.' }
[IO.File]::WriteAllText($envPath,$created)
function docker {
    $global:LASTEXITCODE=0
    if ($args[0] -eq 'info') { if ($args -contains '--format') { 'linux' }; return }
    if ($args -contains 'config') {
        $secret=([regex]::Match($created,'(?m)^FACTORY_TOKEN=(.*)$')).Groups[1].Value.Trim()
        @{name='fixture';services=@{
            controller=@{environment=@{FACTORY_TOKEN=$secret};ports=@(@{host_ip='127.0.0.1';published='8000'})}
            web=@{ports=@(@{host_ip='127.0.0.1';published='5175'})}
        }} | ConvertTo-Json -Depth 8 -Compress
        return
    }
    throw 'Active-job guard allowed a Docker mutation.'
}
function Invoke-RestMethod { @(@{state='TRANSCRIBING'}) }
& "$temporary/scripts/start-factory.ps1" -CpuOnly *> (Join-Path $temporary 'active.log')
if ($LASTEXITCODE -ne 1 -or (Get-Content (Join-Path $temporary 'active.log') -Raw) -notmatch 'Active jobs detected') { throw 'Active-job protection failed.' }
Write-Host '4 launcher checks passed: secure first run, repeat preservation, invalid configuration preservation, active-job protection.'
# Leave the isolated temporary fixture available for inspection; it contains no real credentials.
exit 0 # Expected child-script failures must not leak into the CI shell exit code.
