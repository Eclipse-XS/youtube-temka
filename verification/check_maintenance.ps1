$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('factory-maintenance-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path "$fixture/scripts" | Out-Null
foreach ($name in @('stop-factory.ps1','restart-factory.ps1')) {
    Copy-Item -LiteralPath "$repo/scripts/$name" -Destination "$fixture/scripts/$name"
}
@'
param($Role,[switch]$CpuOnly)
[IO.File]::WriteAllText((Join-Path (Split-Path -Parent $PSScriptRoot) 'started'),'yes')
$global:LASTEXITCODE=0
'@ | Set-Content -Encoding utf8 "$fixture/scripts/start-factory.ps1"
$maintenanceState=@{busy=$true;stops=0}
function docker {
    $global:LASTEXITCODE=0
    if ($args -contains 'ps') { 'fixture-container'; return }
    if ($args -contains 'exec') { if ($maintenanceState.busy) { $global:LASTEXITCODE=1 }; return }
    if ($args -contains 'stop') { $maintenanceState.stops++; return }
    throw 'Unexpected maintenance Docker operation.'
}
$rejected=$false
try { & "$fixture/scripts/stop-factory.ps1" *> "$fixture/stop-busy.log" } catch { $rejected=$true }
if (-not $rejected -or $maintenanceState.stops) { throw 'Stop interrupted an active/unverifiable job.' }
$rejected=$false
try { & "$fixture/scripts/restart-factory.ps1" *> "$fixture/restart-busy.log" } catch { $rejected=$true }
if (-not $rejected -or $maintenanceState.stops -or (Test-Path "$fixture/started")) { throw 'Restart bypassed the idle guard.' }
$maintenanceState.busy=$false
& "$fixture/scripts/stop-factory.ps1"
if ($maintenanceState.stops -ne 1) { throw 'Idle stop failed.' }
& "$fixture/scripts/restart-factory.ps1"
if ($maintenanceState.stops -ne 2 -or -not (Test-Path "$fixture/started")) { throw 'Idle restart failed.' }
Write-Host '4 maintenance checks passed: busy stop/restart refused; idle stop/restart completed.'
exit 0
