param([ValidateSet('Controller','Worker')][string]$Role='Controller',[switch]$CpuOnly,[string]$UpstreamRemote='')
$ErrorActionPreference='Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (@(& git status --porcelain).Count) { throw 'Local changes exist. Commit or preserve them before updating; nothing was overwritten.' }
    $remotes=@(& git remote)
    if ($LASTEXITCODE -ne 0) { throw 'Git remote inspection failed.' }
    $candidates=if ($UpstreamRemote) { @($UpstreamRemote) } else { @('upstream','origin')+$remotes | Select-Object -Unique }
    $selected=$null
    foreach ($candidate in $candidates) {
        if ($remotes -notcontains $candidate) { continue }
        # Read the configured identity, independently of an operator's local URL rewrites.
        $url=& git config --get "remote.$candidate.url"
        if ($LASTEXITCODE -eq 0 -and $url -match '^(?:https://github\.com/|git@github\.com:)denusbtw/youtube-temka(?:\.git)?/?$') { $selected=$candidate; break }
    }
    if (-not $selected -and -not $UpstreamRemote -and $remotes -contains 'origin') {
        $originUrl=& git config --get remote.origin.url
        if ($LASTEXITCODE -eq 0 -and $originUrl -match '^(?:https://github\.com/|git@github\.com:)[A-Za-z0-9_.-]+/youtube-temka(?:\.git)?/?$') {
            $selected=if ($remotes -notcontains 'upstream') { 'upstream' } elseif ($remotes -notcontains 'factory-upstream') { 'factory-upstream' } else { $null }
            if ($selected) {
                & git remote add $selected https://github.com/denusbtw/youtube-temka.git
                if ($LASTEXITCODE -ne 0) { throw 'Could not add the canonical upstream remote.' }
                Write-Host "Added canonical remote $selected; existing remotes were preserved. Ancestry will be verified before updating code."
            }
        }
    }
    if (-not $selected) { throw 'No verified upstream remote. Add upstream https://github.com/denusbtw/youtube-temka.git or select its existing name with -UpstreamRemote.' }
    & git fetch --quiet $selected main
    if ($LASTEXITCODE -ne 0) { throw 'Fetch failed.' }
    $target=& git rev-parse --verify FETCH_HEAD
    if ($LASTEXITCODE -ne 0 -or $target -notmatch '^[0-9a-f]{40}$') { throw 'Fetched main commit could not be verified.' }
    & git merge-base --is-ancestor HEAD $target
    $forward=$LASTEXITCODE
    if ($forward -gt 1) { throw 'Git ancestry inspection failed.' }
    if ($forward -eq 1) {
        & git merge-base --is-ancestor $target HEAD
        if ($LASTEXITCODE -ne 0) { throw 'History diverged; preserve and review the branch before merging.' }
        Write-Host 'Fetched main is already included. Local commits are preserved; they are not claimed as merged upstream.'
    }
    $service=if ($Role -eq 'Controller') { 'controller' } else { 'worker' }
    if ($Role -eq 'Controller') {
        $probe=@'
from factory import store
if any(j['state'] not in ('READY','PUBLISHED','FAILED','BLOCKED','CANCELLED') for j in store.list_jobs()):
    raise SystemExit('Active jobs detected; update postponed without changing application code.')
with store.connect() as db:
    if db.execute("SELECT COUNT(*) FROM publications WHERE state='PUBLISHING'").fetchone()[0]:
        raise SystemExit('Active publishing detected; update postponed.')
print('Controller queue is idle.')
'@
        $probe | & docker compose --profile $Role.ToLower() exec -T $service python -
        if ($LASTEXITCODE -ne 0) { throw 'Active-job safety check failed; update stopped.' }
    }
    & docker compose --profile $Role.ToLower() exec -T $service python -m factory.deployment backup
    if ($LASTEXITCODE -ne 0) { throw 'Persistent database backup failed; update stopped.' }
    if ($forward -eq 0) {
        & git merge --ff-only $target
        if ($LASTEXITCODE -ne 0) { throw 'Fast-forward failed.' }
    }
    & "$PSScriptRoot/start-factory.ps1" -Role $Role -CpuOnly:$CpuOnly
    if ($LASTEXITCODE -ne 0) { throw 'Updated deployment failed readiness.' }
    Write-Host "Upstream ($selected/main): $target"
    Write-Host ('Local HEAD: '+(& git rev-parse HEAD))
} finally { Pop-Location }
