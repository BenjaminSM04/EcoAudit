[CmdletBinding()]
param(
    [string]$Datos = (Join-Path $env:LOCALAPPDATA 'EcoAuditFeria'),
    [ValidateRange(1, 65535)][int]$PuertoApi = 8000,
    [ValidateRange(1, 65535)][int]$PuertoWeb = 8080
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\comun.ps1"

$total = [Diagnostics.Stopwatch]::StartNew()
$Datos = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Datos)
$fallo = $false
foreach ($puerto in @($PuertoWeb, $PuertoApi) | Select-Object -Unique) {
    try {
        Stop-ProcesoFeria (Join-Path $Datos "proceso-$puerto.json")
        if (Test-PuertoOcupado $puerto) {
            throw "El puerto $puerto sigue ocupado. Comprueba que -Datos y los puertos coincidan con los usados al iniciar."
        }
        Write-Host "Puerto $puerto libre."
    } catch {
        Write-Error -Message $_.Exception.Message -ErrorAction Continue
        $fallo = $true
    }
}
if ($fallo) {
    exit 1
}
Write-Host ('Demo detenida en {0:F2} s.' -f $total.Elapsed.TotalSeconds)
