$raiz = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).ProviderPath
$backend = Join-Path $raiz 'backend'
$frontend = Join-Path $raiz 'frontend'
$pythonVenv = Join-Path $backend '.venv\Scripts\python.exe'

function Invoke-Paso {
    param([string]$Nombre, [string]$Programa, [string[]]$Argumentos)

    Write-Host ">> $Nombre"
    $reloj = [Diagnostics.Stopwatch]::StartNew()
    & $Programa @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw "$Nombre falló (código $LASTEXITCODE)."
    }
    Write-Host ('   Tiempo: {0:F2} s' -f $reloj.Elapsed.TotalSeconds)
}

function Get-ClaveAleatoria {
    $bytes = New-Object byte[] 24
    $generador = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generador.GetBytes($bytes)
        return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
    } finally {
        $generador.Dispose()
    }
}

function Set-EntornoFeria {
    param([string]$Directorio)

    $archivo = Join-Path $Directorio '.clave-sesiones'
    if (-not (Test-Path -LiteralPath $archivo -PathType Leaf)) {
        throw "Falta $archivo. Ejecuta preparar.cmd primero."
    }
    $clave = (Get-Content -LiteralPath $archivo -Raw).Trim()
    if (-not $clave) {
        throw "La clave de sesiones está vacía en $archivo."
    }
    $base = (Join-Path $Directorio 'feria.db').Replace('\', '/')
    $env:ECOAUDIT_DATABASE_URL = "sqlite:///$base"
    $env:ECOAUDIT_STORAGE_DIR = Join-Path $Directorio 'almacenamiento'
    $env:ECOAUDIT_SECRET_KEY = $clave
    $env:ECOAUDIT_INLINE_WORKER = 'true'
    $env:PYTHONUTF8 = '1'
}

function Test-PuertoOcupado {
    param([int]$Puerto)

    $escuchas = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return $Puerto -in $escuchas.Port
}

function Stop-ProcesoFeria {
    param([string]$Registro)

    if (-not (Test-Path -LiteralPath $Registro -PathType Leaf)) {
        return
    }
    $identidad = Get-Content -LiteralPath $Registro -Raw | ConvertFrom-Json
    $proceso = Get-Process -Id $identidad.Id -ErrorAction SilentlyContinue
    if ($proceso -and $proceso.StartTime.ToUniversalTime().Ticks.ToString() -eq $identidad.Inicio) {
        # Windows puede ejecutar el Python del venv mediante un proceso hijo.
        & taskkill.exe /PID $proceso.Id /T /F | Out-Null
        if ($LASTEXITCODE -ne 0 -and -not $proceso.HasExited) {
            throw "No se pudo detener el proceso de la feria (PID $($proceso.Id))."
        }
    }
    Remove-Item -LiteralPath $Registro
}
