param([Parameter(Mandatory)] [string] $Destino)

. "$PSScriptRoot/respaldo-comun.ps1"
Invoke-OperacionEcoAudit -Modo respaldo -Destino $Destino
