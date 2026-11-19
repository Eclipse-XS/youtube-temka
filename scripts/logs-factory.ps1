param([ValidateSet('Controller','Worker')][string]$Role='Controller',[int]$Tail=100)
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $services=if ($Role -eq 'Controller') { @('web','controller','ollama') } else { @('worker','ollama') }
    & docker compose --profile $Role.ToLower() logs --tail $Tail @services
    exit $LASTEXITCODE
} finally { Pop-Location }
