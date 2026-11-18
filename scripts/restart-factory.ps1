param([ValidateSet('Controller','Worker')][string]$Role='Controller',[switch]$CpuOnly)
& "$PSScriptRoot/stop-factory.ps1" -Role $Role
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& "$PSScriptRoot/start-factory.ps1" -Role $Role -CpuOnly:$CpuOnly
