$ErrorActionPreference = 'Stop'

try {
    $docker = (Get-Command docker.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $docker) {
        $docker = @(
            (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe')
            (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe')
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if (-not $docker) { throw 'Instala Docker Desktop para Windows x64.' }
    }
    Push-Location -LiteralPath (Join-Path $PSScriptRoot '..\..')
    try {
        & $docker compose stop
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo detener la demo. Comprueba que Docker Desktop esté abierto.' }
        Write-Host 'Demo detenida. Los datos se conservan. Reanuda con docker compose up -d o con docker-demo.cmd.'
    } finally {
        Pop-Location
    }
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
