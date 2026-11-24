# Real temporary Git remotes; Docker/launcher are isolated substitutes.
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('factory-update-'+[Guid]::NewGuid().ToString('N'))
$seed=Join-Path $fixture 'seed'
$remote=Join-Path $fixture 'remote.git'
$consumer=Join-Path $fixture 'consumer'
$marker=Join-Path $fixture 'started'
$oldMarker=$env:FACTORY_UPDATE_TEST_MARKER
$env:FACTORY_UPDATE_TEST_MARKER=$marker
function GitOk([string[]]$Arguments) {
    & git @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Fixture Git failed: $($Arguments[0])" }
}
function InvokeUpdate {
    & "$consumer/scripts/update-factory.ps1" *> (Join-Path $fixture 'update.log')
}
function docker {
    $global:LASTEXITCODE=0
    if ($args -contains 'backup') { 'Consistent test backup acknowledged.'; return }
    if ($args[-1] -eq '-') { 'Controller queue is idle.'; return }
    throw 'Unexpected Docker operation in isolated updater test.'
}
try {
    New-Item -ItemType Directory -Force -Path "$seed/scripts" | Out-Null
    Copy-Item -LiteralPath "$repo/scripts/update-factory.ps1" -Destination "$seed/scripts/update-factory.ps1"
    @'
param($Role,[switch]$CpuOnly)
if ((Get-Content revision.txt -Raw).Trim() -ne '2') { throw 'New code was not deployed.' }
[IO.File]::WriteAllText($env:FACTORY_UPDATE_TEST_MARKER,'started')
$global:LASTEXITCODE=0
'@ | Set-Content -Encoding utf8 "$seed/scripts/start-factory.ps1"
    [IO.File]::WriteAllText("$seed/.gitignore",".env`n")
    [IO.File]::WriteAllText("$seed/revision.txt",'1')
    GitOk @('init','--quiet','--initial-branch=main',$seed)
    GitOk @('-C',$seed,'config','user.name','Deployment tests')
    GitOk @('-C',$seed,'config','user.email','tests@example.invalid')
    GitOk @('-C',$seed,'add','.')
    GitOk @('-C',$seed,'commit','--quiet','-m','Fixture baseline')
    GitOk @('init','--quiet','--bare','--initial-branch=main',$remote)
    GitOk @('-C',$seed,'remote','add','origin',$remote)
    GitOk @('-C',$seed,'push','--quiet','origin','main')
    GitOk @('clone','--quiet',$remote,$consumer)
    GitOk @('-C',$consumer,'config','user.name','Deployment tests')
    GitOk @('-C',$consumer,'config','user.email','tests@example.invalid')
    GitOk @('-C',$consumer,'remote','set-url','origin','https://github.com/Eclipse-XS/youtube-temka.git')
    $localUrl=([Uri]$remote).AbsoluteUri
    GitOk @('-C',$consumer,'config',"url.$localUrl.insteadOf",'https://github.com/denusbtw/youtube-temka.git')
    [IO.File]::WriteAllText("$consumer/.env",'existing configuration remains private')
    [IO.File]::WriteAllText("$seed/revision.txt",'2')
    GitOk @('-C',$seed,'commit','--quiet','-am','Fixture update')
    GitOk @('-C',$seed,'push','--quiet','origin','main')
    $expected=& git -C $seed rev-parse HEAD
    InvokeUpdate
    if (-not (Test-Path $marker) -or (& git -C $consumer rev-parse HEAD) -ne $expected) { throw 'Fork/upstream fast-forward failed.' }
    if ((& git -C $consumer config --get remote.upstream.url) -ne 'https://github.com/denusbtw/youtube-temka.git') { throw 'Canonical upstream bootstrap failed.' }
    [IO.File]::WriteAllText("$seed/upstream.txt",'configured-upstream update')
    GitOk @('-C',$seed,'add','upstream.txt')
    GitOk @('-C',$seed,'commit','--quiet','-m','Configured upstream update')
    GitOk @('-C',$seed,'push','--quiet','origin','main')
    $expected=& git -C $seed rev-parse HEAD
    InvokeUpdate
    if ((& git -C $consumer rev-parse HEAD) -ne $expected) { throw 'Configured fork/upstream fast-forward failed.' }
    InvokeUpdate
    if ((& git -C $consumer rev-parse HEAD) -ne $expected) { throw 'Repeated update changed history.' }
    GitOk @('-C',$consumer,'remote','set-url','origin','https://github.com/denusbtw/youtube-temka.git')
    GitOk @('-C',$consumer,'remote','remove','upstream')
    InvokeUpdate
    [IO.File]::WriteAllText("$consumer/local.txt",'preserved local commit')
    GitOk @('-C',$consumer,'add','local.txt')
    GitOk @('-C',$consumer,'commit','--quiet','-m','Local ahead commit')
    $ahead=& git -C $consumer rev-parse HEAD
    InvokeUpdate
    if ((& git -C $consumer rev-parse HEAD) -ne $ahead) { throw 'Ahead branch was discarded.' }
    [IO.File]::WriteAllText("$consumer/local.txt",'uncommitted edit')
    $rejected=$false
    try { InvokeUpdate } catch { $rejected=$true }
    if (-not $rejected -or [IO.File]::ReadAllText("$consumer/local.txt") -ne 'uncommitted edit') { throw 'Dirty checkout was not protected.' }
    GitOk @('-C',$consumer,'commit','--quiet','-am','Preserve edit')
    $beforeDivergence=& git -C $consumer rev-parse HEAD
    [IO.File]::WriteAllText("$seed/revision.txt",'3')
    GitOk @('-C',$seed,'commit','--quiet','-am','Diverged upstream')
    GitOk @('-C',$seed,'push','--quiet','origin','main')
    $rejected=$false
    try { InvokeUpdate } catch { $rejected=$true }
    if (-not $rejected -or (& git -C $consumer rev-parse HEAD) -ne $beforeDivergence) { throw 'Diverged history was not protected.' }
    if ([IO.File]::ReadAllText("$consumer/.env") -ne 'existing configuration remains private') { throw 'Configuration was replaced.' }
    Write-Host '7 updater checks passed: fork-only bootstrap, fork/upstream fast-forward, repeated update, canonical origin, local-ahead preservation, dirty protection, divergence protection. Configuration preserved.'
} finally { $env:FACTORY_UPDATE_TEST_MARKER=$oldMarker }
exit 0
