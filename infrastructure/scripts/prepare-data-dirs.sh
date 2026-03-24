#!/bin/bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

DATA_ROOT="${PROJECT_ROOT}/data"
DATA_DIRS=(
    "${DATA_ROOT}/postgres"
    "${DATA_ROOT}/redis"
    "${DATA_ROOT}/minio"
    "${DATA_ROOT}/etcd"
    "${DATA_ROOT}/minio-milvus"
    "${DATA_ROOT}/milvus"
    "${DATA_ROOT}/funasr-model-cache"
)

for dir in "${DATA_DIRS[@]}"; do
    mkdir -p "$dir"
done

chmod 700 "${DATA_ROOT}/postgres" "${DATA_ROOT}/redis" 2>/dev/null || true
