param([ValidateSet('Controller','Worker')][string]$Role='Controller')
$ErrorActionPreference='Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $services=if ($Role -eq 'Controller') { @('web','controller','ollama') } else { @('worker','ollama') }
    & docker compose --profile $Role.ToLower() stop @services
    if ($LASTEXITCODE -ne 0) { throw 'Container stop failed.' }
} finally { Pop-Location }
