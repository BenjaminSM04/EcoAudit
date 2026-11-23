#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/respaldo-comun.sh"
if [[ $# -ne 1 ]]; then
    printf 'Uso: bash tools/respaldo.sh DIRECTORIO_DE_DESTINO\n' >&2
    exit 2
fi
operar respaldo "$1"
