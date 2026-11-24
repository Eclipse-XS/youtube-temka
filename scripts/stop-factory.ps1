param([ValidateSet('Controller','Worker')][string]$Role='Controller')
$ErrorActionPreference='Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $service=if ($Role -eq 'Controller') { 'controller' } else { 'worker' }
    $container=& docker compose --profile $Role.ToLower() ps -q $service
    if ($LASTEXITCODE -ne 0) { throw 'Container inspection failed; nothing was stopped.' }
    if ($container) {
        $probe=if ($Role -eq 'Controller') {
@'
from factory import store
if any(j['state'] not in ('READY','PUBLISHED','FAILED','BLOCKED','CANCELLED') for j in store.list_jobs()):
    raise SystemExit('Active processing jobs detected; nothing was stopped.')
with store.connect() as db:
    if db.execute("SELECT COUNT(*) FROM publications WHERE state='PUBLISHING'").fetchone()[0]:
        raise SystemExit('Active publishing detected; nothing was stopped.')
print('Controller processing/publishing is idle.')
'@
        } else {
@'
import os,httpx
from factory import config
with httpx.Client(timeout=15,trust_env=False) as client:
    response=client.get(os.environ['CONTROLLER_URL'].rstrip('/')+'/api/jobs',headers={'Authorization':'Bearer '+config.TOKEN})
    response.raise_for_status()
    if any(j.get('worker')==os.environ['WORKER_ID'] and j['state'] not in ('READY','PUBLISHED','FAILED','BLOCKED','CANCELLED') for j in response.json()):
        raise SystemExit('Active remote worker job detected; nothing was stopped.')
print('Remote worker is idle.')
'@
        }
        $probe | & docker compose --profile $Role.ToLower() exec -T $service python -
        if ($LASTEXITCODE -ne 0) { throw 'Idle status could not be verified; nothing was stopped.' }
    }
    $services=if ($Role -eq 'Controller') { @('web','controller','ollama') } else { @('worker','ollama') }
    & docker compose --profile $Role.ToLower() stop @services
    if ($LASTEXITCODE -ne 0) { throw 'Container stop failed.' }
} finally { Pop-Location }
