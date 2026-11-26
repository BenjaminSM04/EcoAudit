[CmdletBinding()]
param(
    [string]$Datos = (Join-Path $env:LOCALAPPDATA 'EcoAuditFeria'),
    [ValidateRange(1, 65535)][int]$PuertoApi = 8000,
    [ValidateRange(1, 65535)][int]$PuertoWeb = 8080,
    [switch]$SinNavegador
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\comun.ps1"

function Wait-SaludFeria {
    param([string]$Url)

    while ($inicio.Elapsed.TotalSeconds -lt 60) {
        if ($procesos.Where({ $_.HasExited }).Count) {
            throw 'Uno de los servicios se cerró durante el arranque. Revisa el mensaje en sus ventanas.'
        }
        try {
            $salud = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 1
            if ($salud.status -eq 'ok') {
                return
            }
        } catch {
            # El servidor aún puede estar arrancando.
        }
        Start-Sleep -Milliseconds 300
    }
    throw "No hubo respuesta saludable de $Url/api/health en 60 s."
}

$procesos = @()
$registros = @()
try {
    $total = [Diagnostics.Stopwatch]::StartNew()
    $Datos = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Datos)
    if ($PuertoApi -eq $PuertoWeb) {
        throw 'La API y la web deben usar puertos distintos.'
    }
    foreach ($puerto in $PuertoApi, $PuertoWeb) {
        if (Test-PuertoOcupado $puerto) {
            throw "El puerto $puerto ya está ocupado. Elige otro puerto con -PuertoApi o -PuertoWeb."
        }
    }
    $credenciales = Join-Path $Datos 'credenciales.txt'
    if (-not (Test-Path -LiteralPath $pythonVenv -PathType Leaf) -or
        -not (Test-Path -LiteralPath $credenciales -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $Datos 'feria.db') -PathType Leaf)) {
        throw 'Falta preparar la demo. Ejecuta preparar.cmd con la carpeta de datos indicada.'
    }
    Set-EntornoFeria $Datos
    $node = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $vite = Join-Path $frontend 'node_modules\vite\bin\vite.js'
    if (-not $node -or -not (Test-Path -LiteralPath $vite -PathType Leaf)) {
        throw 'Falta Node.js o la instalación local de Vite. Instala Node.js 24 LTS y ejecuta preparar.cmd con internet.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontend 'dist\index.html') -PathType Leaf)) {
        $npm = Get-Command npm.cmd -CommandType Application | Select-Object -First 1
        Push-Location -LiteralPath $frontend
        try {
            Invoke-Paso 'Compilar el frontend (npm run build)' $npm.Source @('run', 'build')
        } finally {
            Pop-Location
        }
    }

    $urlApi = "http://127.0.0.1:$PuertoApi"
    $urlWeb = "http://127.0.0.1:$PuertoWeb"
    $env:ECOAUDIT_API_PROXY = $urlApi
    $servicios = @(
        @{ Nombre = 'API'; Puerto = $PuertoApi; Ejecutable = $pythonVenv; Carpeta = $backend
           Argumentos = "-m uvicorn app.main:app --host 127.0.0.1 --port $PuertoApi" }
        @{ Nombre = 'web'; Puerto = $PuertoWeb; Ejecutable = $node.Source; Carpeta = $frontend
           Argumentos = ('"{0}" preview --host 127.0.0.1 --port {1} --strictPort' -f $vite, $PuertoWeb) }
    )
    $inicio = [Diagnostics.Stopwatch]::StartNew()
    foreach ($servicio in $servicios) {
        Write-Host ">> Iniciando $($servicio.Nombre) en el puerto $($servicio.Puerto)"
        $registro = Join-Path $Datos "proceso-$($servicio.Puerto).json"
        $proceso = Start-Process -FilePath $servicio.Ejecutable -ArgumentList $servicio.Argumentos `
            -WorkingDirectory $servicio.Carpeta -WindowStyle Minimized -PassThru
        $procesos += $proceso
        @{ Id = $proceso.Id; Inicio = $proceso.StartTime.ToUniversalTime().Ticks.ToString() } |
            ConvertTo-Json -Compress | Set-Content -LiteralPath $registro -Encoding Ascii
        $registros += $registro
    }
    Wait-SaludFeria $urlApi
    Write-Host ('   API lista a los {0:F2} s.' -f $inicio.Elapsed.TotalSeconds)
    Wait-SaludFeria $urlWeb
    Write-Host ('   Proxy web listo a los {0:F2} s.' -f $inicio.Elapsed.TotalSeconds)

    $contenido = Get-Content -LiteralPath $credenciales -Encoding UTF8
    $contenido -replace '^URL: .*$', "URL: $urlWeb" |
        Set-Content -LiteralPath $credenciales -Encoding UTF8
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    foreach ($registro in $registros) {
        try {
            Stop-ProcesoFeria $registro
        } catch {
            Write-Warning $_.Exception.Message
        }
    }
    foreach ($proceso in $procesos) {
        if (-not $proceso.HasExited) {
            & taskkill.exe /PID $proceso.Id /T /F | Out-Null
        }
    }
    exit 1
}

Write-Host ('Demo lista en {0:F2} s.' -f $total.Elapsed.TotalSeconds)
Write-Host "URL: $urlWeb"
Write-Host "Credenciales: $credenciales"
if (-not $SinNavegador) {
    Start-Process $urlWeb
}
