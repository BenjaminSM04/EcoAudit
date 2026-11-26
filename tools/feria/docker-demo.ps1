[CmdletBinding()]
param(
    [string]$Datos = (Join-Path $env:LOCALAPPDATA 'EcoAuditFeria'),
    [string]$ZipModelo,
    [string]$ZipImagenes,
    [ValidateRange(1, 65535)][int]$PuertoWeb = 8080,
    [switch]$SinNavegador,
    [switch]$SinCompilar
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\comun.ps1"

function Test-Docker([int]$TiempoMs) {
    $inicio = New-Object Diagnostics.ProcessStartInfo
    $inicio.FileName = $docker
    $inicio.Arguments = 'info --format {{.ServerVersion}}'
    $inicio.UseShellExecute = $false
    $inicio.CreateNoWindow = $true
    $inicio.RedirectStandardOutput = $true
    $inicio.RedirectStandardError = $true
    $proceso = [Diagnostics.Process]::Start($inicio)
    try {
        $salida = $proceso.StandardOutput.ReadToEndAsync()
        $errores = $proceso.StandardError.ReadToEndAsync()
        if (-not $proceso.WaitForExit($TiempoMs)) {
            $proceso.Kill()
            return $false
        }
        return $proceso.ExitCode -eq 0
    } finally {
        $proceso.Dispose()
    }
}

function Invoke-Compose {
    & $docker compose @archivosCompose @args
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose falló (código $LASTEXITCODE). Revisa la salida anterior."
    }
}

function Expand-RecursoFeria([string]$Archivo, [string]$Nombre, [string]$Hash, [string]$Carpeta) {
    $cache = Join-Path $descargas $Nombre
    $descargar = -not $Archivo -and -not (Test-Path -LiteralPath $cache -PathType Leaf)
    if (-not $Archivo) { $Archivo = $cache }
    if ($descargar) {
        $Archivo = "$cache.$([guid]::NewGuid()).parcial"
    } elseif (-not (Test-Path -LiteralPath $Archivo -PathType Leaf)) {
        throw "No se encontró el ZIP: $Archivo"
    }

    try {
        if ($descargar) {
            Write-Host ">> Descargando $Nombre desde GitHub"
            $reloj = [Diagnostics.Stopwatch]::StartNew()
            $tlsAnterior = [Net.ServicePointManager]::SecurityProtocol
            $progresoAnterior = $ProgressPreference
            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                $ProgressPreference = 'SilentlyContinue'
                Invoke-WebRequest -UseBasicParsing -Uri "$release/$Nombre" -OutFile $Archivo
            } finally {
                [Net.ServicePointManager]::SecurityProtocol = $tlsAnterior
                $ProgressPreference = $progresoAnterior
            }
            Write-Host ('   Descarga completada en {0:F1} s.' -f $reloj.Elapsed.TotalSeconds)
        } else {
            Write-Host ">> Usando ZIP local: $Archivo"
        }

        if ((Get-FileHash -LiteralPath $Archivo -Algorithm SHA256).Hash -ne $Hash) {
            Remove-Item -LiteralPath $Archivo -Force
            throw "SHA-256 incorrecto para $Nombre. Se borró el ZIP. Obtén una copia íntegra del release modelo-v1.0.0 y reintenta."
        }
        Write-Host "   SHA-256 verificado: $Nombre"
        if ($descargar) {
            Move-Item -LiteralPath $Archivo -Destination $cache -Force
            $Archivo = $cache
        }
    } finally {
        if ($descargar -and $Archivo -ne $cache -and (Test-Path -LiteralPath $Archivo -PathType Leaf)) {
            Remove-Item -LiteralPath $Archivo -Force
        }
    }

    Write-Host ">> Extrayendo $Nombre en $Datos"
    Expand-Archive -LiteralPath $Archivo -DestinationPath $Datos -Force
    $destino = Join-Path $Datos $Carpeta
    if (-not (Test-Path -LiteralPath $destino -PathType Container)) {
        throw "El ZIP $Nombre debe contener la carpeta $Carpeta."
    }
    return $destino
}

try {
    $total = [Diagnostics.Stopwatch]::StartNew()
    $Datos = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Datos)
    if ($ZipModelo) { $ZipModelo = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ZipModelo) }
    if ($ZipImagenes) { $ZipImagenes = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ZipImagenes) }
    $docker = (Get-Command docker.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $docker) {
        # Una sesión de Windows abierta antes de instalar Docker puede tener un PATH anterior.
        $docker = @(
            (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe')
            (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe')
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if (-not $docker) {
            throw 'Instala Docker Desktop (Windows x64), reinicia Windows y abre Docker Desktop.'
        }
    }

    Write-Host '>> Comprobando el motor de Docker'
    $espera = [Diagnostics.Stopwatch]::StartNew()
    if (-not (Test-Docker 5000)) {
        $escritorio = @(
            (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe')
            (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe')
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if ($escritorio) {
            Start-Process -FilePath $escritorio -WindowStyle Hidden
        }
        Write-Host '   Esperando a Docker Desktop (hasta 3 minutos).'
        $disponible = $false
        while ($espera.Elapsed.TotalSeconds -lt 180) {
            $restante = [int](180000 - $espera.Elapsed.TotalMilliseconds)
            if (Test-Docker ([Math]::Max(1, [Math]::Min(5000, $restante)))) {
                $disponible = $true
                break
            }
            if ($espera.Elapsed.TotalSeconds -lt 178) { Start-Sleep -Seconds 2 }
        }
        if (-not $disponible) {
            throw 'Docker no responde. Abre Docker Desktop, acepta sus términos y espera el motor de contenedores Linux. Si WSL falla, ejecuta wsl --update o instala WSL 2 con wsl --install y reinicia Windows.'
        }
    }

    $raiz = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
    $envAnterior = $env:ECOAUDIT_DEMO
    $puertoAnterior = $env:ECOAUDIT_FERIA_PUERTO
    Push-Location -LiteralPath $raiz
    try {
        $archivoEnv = Join-Path $raiz '.env'
        if (-not (Test-Path -LiteralPath $archivoEnv)) {
            Set-Content -LiteralPath $archivoEnv -Encoding Ascii -Value @(
                "POSTGRES_PASSWORD=$(Get-ClaveAleatoria)"
                "ECOAUDIT_SECRET_KEY=$(Get-ClaveAleatoria)"
                'ECOAUDIT_DEMO=1'
            )
            Write-Host '>> Configuración .env creada con claves aleatorias.'
        } else {
            $lineasDemo = Select-String -LiteralPath $archivoEnv -Pattern '^\s*(?:export\s+)?ECOAUDIT_DEMO\s*=' | Select-Object -Last 1
            if ($lineasDemo.Line -notmatch '^\s*(?:export\s+)?ECOAUDIT_DEMO\s*=\s*(?:1|"1"|''1'')(?:\s+#.*|\s*)$') {
                [IO.File]::AppendAllText($archivoEnv, "`r`nECOAUDIT_DEMO=1`r`n")
                Write-Host '>> ECOAUDIT_DEMO=1 agregado al .env existente.'
            }
        }
        $env:ECOAUDIT_DEMO = '1'
        $archivosCompose = @()
        if ($PuertoWeb -ne 8080) {
            $env:ECOAUDIT_FERIA_PUERTO = [string]$PuertoWeb
            $archivosCompose = @('-f', 'docker-compose.yml', '-f', (Join-Path $PSScriptRoot 'docker-puerto.yml'))
        }

        $reloj = [Diagnostics.Stopwatch]::StartNew()
        if ($SinCompilar) {
            Write-Host '>> Iniciando con las imágenes Docker que ya están en el equipo'
            Invoke-Compose up --no-build --pull never -d --wait --wait-timeout 180
        } else {
            Write-Host '>> Compilando e iniciando Docker Compose; esperando que la API esté healthy'
            Invoke-Compose up --build -d --wait --wait-timeout 180
        }
        Write-Host ('   Compose listo en {0:F1} s.' -f $reloj.Elapsed.TotalSeconds)

        $release = 'https://github.com/BenjaminSM04/EcoAudit/releases/download/modelo-v1.0.0'
        $descargas = Join-Path $Datos 'descargas'
        [void][IO.Directory]::CreateDirectory($descargas)
        $modelo = Expand-RecursoFeria $ZipModelo 'modelo-paper-resnet18-control-v1.0.0.zip' `
            'e1f251ef299c9b823bcf8a7723ca0fce2ffd47eca6c596928ed19f8351fa058a' 'paper-resnet18-control'
        $imagenes = Expand-RecursoFeria $ZipImagenes 'imagenes-demo-bus-bra.zip' `
            'acd1a6230031728e6cee5eaa537557b3ffe3afa2fe7f8735f9f0d2d5f1012572' 'imagenes-demo'

        $consulta = 'from app.db import new_session; from app.registry import get_active; model = get_active(new_session()); print(model.name if model else str())'
        $activo = Invoke-Compose exec -T api python -c $consulta
        if ($activo -ne 'paper-v3-resnet18-source-only-matched') {
            Write-Host '>> Registrando y activando el modelo del estudio'
            $modeloContenedor = '/tmp/paper-resnet18-control'
            Invoke-Compose exec -T --user root api rm -rf -- $modeloContenedor
            try {
                Invoke-Compose cp $modelo "api:$modeloContenedor"
                Invoke-Compose exec -T api python -m app.cli register-model $modeloContenedor --activate
            } finally {
                Invoke-Compose exec -T --user root api rm -rf -- $modeloContenedor
            }
        } else {
            Write-Host ">> El modelo del estudio ya está activo: $activo"
        }

        $url = "http://localhost:$PuertoWeb"
        $credenciales = Join-Path $Datos 'credenciales-docker.txt'
        if (Test-Path -LiteralPath $credenciales -PathType Leaf) {
            $lineas = @(Get-Content -LiteralPath $credenciales -Encoding UTF8 | Where-Object { $_ -match '^Clave: \S{10,}$' })
            if ($lineas.Count -ne 1) { throw "No se encontró una clave válida en $credenciales." }
            $clave = $lineas[0].Substring('Clave: '.Length)
        } else {
            $clave = Get-ClaveAleatoria
        }
        # Guarda la clave antes de crear las cuentas para poder reintentar con la misma.
        Set-Content -LiteralPath $credenciales -Encoding UTF8 -Value @(
            "URL: $url"
            "Clave: $clave"
            ''
            'admin@ecoaudit.test (administración)'
            'medico1@ecoaudit.test (medicina)'
            'medico2@ecoaudit.test (medicina)'
            'investigador@ecoaudit.test (investigación)'
        )
        Write-Host '>> Preparando las cuentas y los casos de demostración'
        Invoke-Compose exec -T api python -m app.cli seed-demo --password $clave

        Write-Host '>> Comprobando la API a través de la interfaz web'
        $salud = Invoke-RestMethod -UseBasicParsing -TimeoutSec 15 -Uri "http://127.0.0.1:$PuertoWeb/api/health"
        if ($salud.status -ne 'ok') { throw 'La comprobación HTTP de la API no devolvió el estado ok.' }
        Write-Host ('Demo disponible en {0} ({1:F1} s en total).' -f $url, $total.Elapsed.TotalSeconds)
        Write-Host "Credenciales: $credenciales"
        Write-Host "Imágenes de ejemplo: $imagenes"
        if (-not $SinNavegador) { Start-Process $url }
    } finally {
        $env:ECOAUDIT_DEMO = $envAnterior
        $env:ECOAUDIT_FERIA_PUERTO = $puertoAnterior
        Pop-Location
    }
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
