#!/usr/bin/env bash

ruta_docker() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -am -- "$1"
    else
        printf '%s\n' "$1"
    fi
}

almacenamiento() {
    local montaje=$1
    shift
    docker compose run --rm --no-deps -T --user 0 --entrypoint sh \
        --volume "$montaje" api -ec "$1"
}

limpiar() {
    local estado=$?
    trap - EXIT
    if [[ -n $temporal_db ]]; then
        docker compose exec -T db rm -f -- "$temporal_db" || estado=1
    fi
    if [[ $pausa == 1 && ( $modo == respaldo || $estado == 0 ) && ${#reiniciar[@]} != 0 ]]; then
        docker compose start --wait "${reiniciar[@]}" || estado=1
    elif [[ $pausa == 1 && $modo == restauracion && $estado != 0 ]]; then
        printf 'Restauración interrumpida. Los escritores quedan detenidos.\n' >&2
    fi
    if [[ -n $preparacion ]]; then
        rmdir -- "$preparacion" 2>/dev/null ||
            printf 'Revise el respaldo parcial en %s\n' "$preparacion" >&2
    fi
    exit "$estado"
}

operar() {
    modo=$1
    local destino=$2 ruta montaje servicio activos fecha
    # Evita que Git Bash modifique las rutas internas de los contenedores.
    export MSYS_NO_PATHCONV=1
    umask 077
    temporal_db='' preparacion='' pausa=0 reiniciar=()
    trap limpiar EXIT

    if [[ $modo == respaldo ]]; then
        mkdir -p -- "$destino"
        destino=$(cd -- "$destino" && pwd -P)
        fecha=$(date -u +'%Y%m%dT%H%M%SZ')
        preparacion=$(mktemp -d "$destino/.parcial-$fecha-XXXXXX")
        ruta=$preparacion
    else
        ruta=$(cd -- "$destino" && pwd -P)
        [[ -s $ruta/postgres.dump && -s $ruta/storage.tar.gz ]] || {
            printf 'Falta postgres.dump o storage.tar.gz en el respaldo.\n' >&2
            return 1
        }
    fi
    ruta=$(ruta_docker "$ruta")
    montaje="$ruta:/respaldo"
    activos=$(docker compose ps --status running --services)
    for servicio in api worker web; do
        if [[ $'\n'$activos$'\n' == *$'\n'"$servicio"$'\n'* ]]; then
            reiniciar+=("$servicio")
        fi
    done
    temporal_db=$(docker compose exec -T db mktemp /tmp/ecoaudit-operacion.XXXXXX)

    if [[ $modo == restauracion ]]; then
        docker compose cp "$ruta/postgres.dump" "db:$temporal_db"
        docker compose exec -T db pg_restore --list "$temporal_db" >/dev/null
        almacenamiento "$montaje:ro" 'tar -tzf /respaldo/storage.tar.gz >/dev/null'
    fi

    pausa=1
    docker compose stop web api worker
    if [[ $modo == respaldo ]]; then
        docker compose exec -T db pg_dump -U ecoaudit -d ecoaudit --format=custom --create --file="$temporal_db"
        docker compose cp "db:$temporal_db" "$ruta/postgres.dump"
        # Cree el archivo como operador para conservar su dueño y permisos en el host.
        : > "$preparacion/storage.tar.gz"
        almacenamiento "$montaje" 'tar -czf /respaldo/storage.tar.gz -C /data .'
        local final="$destino/${preparacion##*/.parcial-}"
        mv -- "$preparacion" "$final"
        preparacion=''
        printf 'Respaldo guardado en %s\n' "$final"
    else
        docker compose exec -T db pg_restore -U ecoaudit -d postgres --clean --if-exists \
            --create --exit-on-error "$temporal_db"
        almacenamiento "$montaje:ro" 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; tar -xzpf /respaldo/storage.tar.gz -C /data'
        printf 'Base de datos y almacenamiento restaurados desde %s\n' "$destino"
    fi
}
