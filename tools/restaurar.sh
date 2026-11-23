#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
    printf 'Uso: bash tools/restaurar.sh DIRECTORIO_DEL_RESPALDO\n' >&2
    exit 2
fi
source "$(dirname -- "${BASH_SOURCE[0]}")/respaldo-comun.sh"
operar restauracion "$1"
