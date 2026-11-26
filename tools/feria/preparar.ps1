[CmdletBinding()]
param(
    [string]$Modelo,
    [string]$Imagenes,
    [string]$Datos = (Join-Path $env:LOCALAPPDATA 'EcoAuditFeria')
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\comun.ps1"

try {
    $total = [Diagnostics.Stopwatch]::StartNew()
    $Datos = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Datos)
    if ($Modelo) {
        $Modelo = (Get-Item -LiteralPath $Modelo).FullName
        if (-not (Test-Path -LiteralPath $Modelo -PathType Container)) {
            throw '-Modelo debe apuntar a la carpeta del bundle ONNX.'
        }
    } elseif (-not (Test-Path -LiteralPath (Join-Path $Datos 'feria.db') -PathType Leaf)) {
        throw 'Indica -Modelo con la ruta a la carpeta del bundle ONNX para la primera preparación.'
    }
    if ($Imagenes) {
        $Imagenes = (Get-Item -LiteralPath $Imagenes).FullName
        if (-not (Test-Path -LiteralPath $Imagenes -PathType Container)) {
            throw '-Imagenes debe apuntar a una carpeta con imágenes de ejemplo.'
        }
    }

    Write-Host '>> Comprobando Python, Node.js y npm'
    $pruebaPython = 'import sys; print(sys.version.split()[0]); sys.exit(sys.version_info < (3, 11))'
    $python = $null
    $opcionesPython = @()
    foreach ($nombre in 'py.exe', 'python.exe') {
        $comando = Get-Command $nombre -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($comando) {
            $opcionesPython = @()
            if ($nombre -eq 'py.exe') {
                $opcionesPython = @('-3.11')
            }
            # El lanzador puede escribir en stderr si Python 3.11 no está instalado.
            $ErrorActionPreference = 'Continue'
            try {
                $versionPython = & $comando.Source @opcionesPython -c $pruebaPython 2>$null
                if ($LASTEXITCODE -eq 0) {
                    $python = $comando.Source
                    break
                }
            } finally {
                $ErrorActionPreference = 'Stop'
            }
        }
    }
    if (-not $python) {
        throw 'Instala Python 3.11 o posterior (Windows x64), agrégalo al PATH y vuelve a abrir la terminal.'
    }
    $node = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $npm = Get-Command npm.cmd -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $node -or -not $npm) {
        throw 'Instala Node.js 24 LTS (Windows x64) con npm, agrega Node al PATH y vuelve a abrir la terminal.'
    }
    $versionNode = [version]((& $node.Source --version).TrimStart('v'))
    if (($versionNode.Major -eq 20 -and $versionNode.Minor -ge 19) -or
        ($versionNode.Major -eq 22 -and $versionNode.Minor -ge 13) -or
        ($versionNode.Major -eq 23 -and $versionNode.Minor -ge 5) -or
        $versionNode.Major -ge 24) {
        Write-Host "   Python $versionPython, Node.js $versionNode"
    } else {
        throw "Node.js $versionNode no cumple los requisitos del lockfile. Instala Node.js 24 LTS (Windows x64)."
    }

    Push-Location -LiteralPath $backend
    try {
        if (-not (Test-Path -LiteralPath $pythonVenv -PathType Leaf)) {
            Invoke-Paso 'Crear el entorno virtual' $python ($opcionesPython + @('-m', 'venv', '.venv'))
        }
        Invoke-Paso 'Comprobar el Python del entorno virtual' $pythonVenv @('-c', $pruebaPython)
        Invoke-Paso 'Instalar el backend (pip install -e .[demo])' $pythonVenv @('-m', 'pip', 'install', '-e', '.[demo]')
    } finally {
        Pop-Location
    }

    Push-Location -LiteralPath $frontend
    try {
        $selloNpm = 'node_modules\.ecoaudit-feria'
        $hashesNpm = (Get-FileHash -LiteralPath 'package.json', 'package-lock.json').Hash
        $firmaNpm = ($hashesNpm -join ':') + ":$versionNode"
        # Vite puede tener abiertos binarios de node_modules mientras sirve la demo.
        if ((Test-Path -LiteralPath $selloNpm -PathType Leaf) -and
            (Get-Content -LiteralPath $selloNpm) -eq $firmaNpm -and
            (Test-Path -LiteralPath 'node_modules\vite\bin\vite.js' -PathType Leaf) -and
            (Test-Path -LiteralPath 'node_modules\.bin\tsc.cmd' -PathType Leaf)) {
            Write-Host '>> npm ci omitido: las dependencias del frontend ya están instaladas.'
        } else {
            Invoke-Paso 'Instalar el frontend (npm ci)' $npm.Source @('ci')
            Set-Content -LiteralPath $selloNpm -Value $firmaNpm -Encoding Ascii
        }
        Invoke-Paso 'Compilar el frontend (npm run build)' $npm.Source @('run', 'build')
    } finally {
        Pop-Location
    }

    [void][IO.Directory]::CreateDirectory($Datos)
    $archivoClave = Join-Path $Datos '.clave-sesiones'
    if (-not (Test-Path -LiteralPath $archivoClave)) {
        Set-Content -LiteralPath $archivoClave -Value (Get-ClaveAleatoria) -Encoding Ascii
    }
    Set-EntornoFeria $Datos
    $credenciales = Join-Path $Datos 'credenciales.txt'

    Push-Location -LiteralPath $backend
    try {
        Invoke-Paso 'Aplicar las migraciones de SQLite' $pythonVenv @('-m', 'app.cli', 'db-upgrade')
        if ($Modelo) {
            Invoke-Paso 'Registrar y activar el modelo del estudio' $pythonVenv @('-m', 'app.cli', 'register-model', $Modelo, '--activate')
        } else {
            $pruebaModelo = 'from app.db import new_session; from app.registry import get_active; import sys; db = new_session(); sys.exit(get_active(db) is None)'
            & $pythonVenv -c $pruebaModelo
            if ($LASTEXITCODE -ne 0) {
                throw 'La base de la feria no tiene un modelo activo. Ejecuta la preparación con -Modelo.'
            }
            Write-Host '>> Se conserva el modelo activo de la feria.'
        }
        if (Test-Path -LiteralPath $credenciales -PathType Leaf) {
            $linea = Get-Content -LiteralPath $credenciales -Encoding UTF8 | Where-Object { $_ -match '^Clave: (\S+)$' }
            if (@($linea).Count -ne 1) {
                throw "No se encontró una clave válida en $credenciales."
            }
            $claveDemo = $linea.Substring('Clave: '.Length)
        } else {
            # Guarda la clave antes de crear las cuentas para poder reintentar con la misma.
            $claveDemo = Get-ClaveAleatoria
            Set-Content -LiteralPath $credenciales -Encoding UTF8 -Value @(
                'URL: http://127.0.0.1:8080'
                "Clave: $claveDemo"
                ''
                'admin@ecoaudit.test (administración)'
                'medico1@ecoaudit.test (medicina)'
                'medico2@ecoaudit.test (medicina)'
                'investigador@ecoaudit.test (investigación)'
            )
        }
        Invoke-Paso 'Preparar las cuentas y los casos de demostración' $pythonVenv @('-m', 'app.cli', 'seed-demo', '--password', $claveDemo)
    } finally {
        Pop-Location
    }

    if ($Imagenes) {
        $reloj = [Diagnostics.Stopwatch]::StartNew()
        $destino = Join-Path $Datos 'imagenes-demo'
        [void][IO.Directory]::CreateDirectory($destino)
        Get-ChildItem -LiteralPath $Imagenes -File | ForEach-Object {
            $copia = Join-Path $destino $_.Name
            if ($_.FullName -ne $copia) {
                Copy-Item -LiteralPath $_.FullName -Destination $copia -Force
            }
        }
        Write-Host ('>> Imágenes copiadas en {0} ({1:F2} s)' -f $destino, $reloj.Elapsed.TotalSeconds)
    }

    Write-Host ('Preparación completada en {0:F2} s.' -f $total.Elapsed.TotalSeconds)
    Write-Host "Datos: $Datos"
    Write-Host "Credenciales: $credenciales"
    Write-Host 'Abre iniciar.cmd para levantar la demo.'
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
