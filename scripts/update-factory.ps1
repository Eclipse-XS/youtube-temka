param([ValidateSet('Controller','Worker')][string]$Role='Controller',[switch]$CpuOnly)
$ErrorActionPreference='Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (@(& git status --porcelain).Count) { throw 'Local changes exist. Commit or preserve them before updating; nothing was overwritten.' }
    $url=& git remote get-url origin
    if ($url -notmatch '^(?:https://github\.com/|git@github\.com:)denusbtw/youtube-temka(?:\.git)?$') { throw 'Unexpected upstream repository.' }
    & git fetch origin main
    if ($LASTEXITCODE -ne 0) { throw 'Fetch failed.' }
    & git merge-base --is-ancestor HEAD origin/main
    if ($LASTEXITCODE -ne 0) { throw 'History diverged; preserve and review the branch before merging.' }
    $service=if ($Role -eq 'Controller') { 'controller' } else { 'worker' }
    & docker compose --profile $Role.ToLower() exec -T $service python -m factory.deployment backup
    if ($LASTEXITCODE -ne 0) { throw 'Persistent database backup failed; update stopped.' }
    & git merge --ff-only origin/main
    if ($LASTEXITCODE -ne 0) { throw 'Fast-forward failed.' }
    & "$PSScriptRoot/start-factory.ps1" -Role $Role -CpuOnly:$CpuOnly
    if ($LASTEXITCODE -ne 0) { throw 'Updated deployment failed readiness.' }
} finally { Pop-Location }
