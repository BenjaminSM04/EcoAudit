function Invoke-Compose {
    & docker compose @args
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose falló ($LASTEXITCODE) en la operación $($args[0])."
    }
}

function Invoke-Almacenamiento([string] $Montaje, [string] $Comando) {
    Invoke-Compose run --rm --no-deps -T --user 0 --entrypoint sh --volume $Montaje api -ec $Comando
}

function Invoke-OperacionEcoAudit([string] $Modo, [string] $Destino) {
    $ErrorActionPreference = 'Stop'
    $temporalDb = $null
    $preparacion = $null
    $pausa = $false
    $terminado = $false
    $reiniciar = @()

    try {
        if ($Modo -eq 'respaldo') {
            [void] [IO.Directory]::CreateDirectory($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destino))
            $Destino = (Resolve-Path -LiteralPath $Destino).Path
            $fecha = (Get-Date).ToUniversalTime().ToString("yyyyMMdd'T'HHmmss'Z'")
            $nombre = "$fecha-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
            $preparacion = Join-Path $Destino ".parcial-$nombre"
            [void] [IO.Directory]::CreateDirectory($preparacion)
            $ruta = $preparacion
        } else {
            $ruta = (Resolve-Path -LiteralPath $Destino).Path
            foreach ($nombre in @('postgres.dump', 'storage.tar.gz')) {
                if ((Get-Item -LiteralPath (Join-Path $ruta $nombre)).Length -le 0) {
                    throw "El archivo $nombre está vacío."
                }
            }
        }
        $volcado = Join-Path $ruta 'postgres.dump'
        $montaje = "${ruta}:/respaldo"
        $activos = @(Invoke-Compose ps --status running --services)
        $reiniciar = @('api', 'worker', 'web' | Where-Object { $_ -in $activos })
        $temporalDb = Invoke-Compose exec -T db mktemp /tmp/ecoaudit-operacion.XXXXXX

        if ($Modo -eq 'restauracion') {
            Invoke-Compose cp $volcado "db:$temporalDb"
            Invoke-Compose exec -T db pg_restore --list $temporalDb | Out-Null
            Invoke-Almacenamiento "${montaje}:ro" 'tar -tzf /respaldo/storage.tar.gz >/dev/null'
        }

        $pausa = $true
        Invoke-Compose stop web api worker
        if ($Modo -eq 'respaldo') {
            Invoke-Compose exec -T db pg_dump -U ecoaudit -d ecoaudit --format=custom --create "--file=$temporalDb"
            Invoke-Compose cp "db:$temporalDb" $volcado
            # Cree el archivo como operador antes de que el contenedor escriba el tar.
            [IO.File]::Create((Join-Path $ruta 'storage.tar.gz')).Dispose()
            Invoke-Almacenamiento $montaje 'tar -czf /respaldo/storage.tar.gz -C /data .'
            $final = Join-Path $Destino $nombre
            [IO.Directory]::Move($preparacion, $final)
            $preparacion = $null
            Write-Output "Respaldo guardado en $final"
        } else {
            Invoke-Compose exec -T db pg_restore -U ecoaudit -d postgres --clean --if-exists --create --exit-on-error $temporalDb
            Invoke-Almacenamiento "${montaje}:ro" 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; tar -xzpf /respaldo/storage.tar.gz -C /data'
            Write-Output "Base de datos y almacenamiento restaurados desde $ruta"
        }
        $terminado = $true
    } finally {
        try {
            if ($temporalDb) {
                Invoke-Compose exec -T db rm -f -- $temporalDb
            }
        } finally {
            if ($pausa -and ($Modo -eq 'respaldo' -or $terminado) -and $reiniciar.Count) {
                Invoke-Compose start --wait @reiniciar
            } elseif ($pausa -and $Modo -eq 'restauracion' -and -not $terminado) {
                Write-Warning 'Restauración interrumpida. Los escritores quedan detenidos.'
            }
            if ($preparacion) {
                if (Get-ChildItem -Force -LiteralPath $preparacion) {
                    Write-Warning "Revise el respaldo parcial en $preparacion"
                } else {
                    [IO.Directory]::Delete($preparacion)
                }
            }
        }
    }
}
