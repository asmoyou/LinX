#!/bin/bash

# LinX (灵枢) - Backup Script
# This script creates backups of the project-local data directories

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Configuration
BACKUP_DIR=${BACKUP_DIR:-"${PROJECT_ROOT}/backups"}
DATA_ROOT="${PROJECT_ROOT}/data"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="dwp_backup_${TIMESTAMP}"

# Create backup directory
mkdir -p "$BACKUP_DIR/$BACKUP_NAME"

print_info "Starting backup: $BACKUP_NAME"

if ! resolve_compose_cmd; then
    print_error "Docker Compose is not installed. Please install docker compose or docker-compose first."
    exit 1
fi

# Backup PostgreSQL
print_info "Backing up PostgreSQL..."
run_compose exec -T postgres pg_dumpall -U "${POSTGRES_USER:-dwp_user}" > "$BACKUP_DIR/$BACKUP_NAME/postgres.sql"
print_success "PostgreSQL backup completed"

# Backup Redis
print_info "Backing up Redis..."
run_compose exec -T redis redis-cli --no-auth-warning -a "${REDIS_PASSWORD:-redis_password_change_me}" SAVE >/dev/null
cp "${DATA_ROOT}/redis/dump.rdb" "$BACKUP_DIR/$BACKUP_NAME/redis.rdb"
print_success "Redis backup completed"

copy_data_dir() {
    local source_name="$1"
    local destination_dir="$BACKUP_DIR/$BACKUP_NAME/$source_name"
    local source_dir="${DATA_ROOT}/$source_name"

    if [ ! -d "$source_dir" ]; then
        print_warning "Skipping missing data directory: ${source_dir}"
        return 0
    fi

    mkdir -p "$destination_dir"
    cp -a "${source_dir}/." "$destination_dir/"
}

print_info "Backing up object storage and vector data directories..."
copy_data_dir "minio"
copy_data_dir "etcd"
copy_data_dir "minio-milvus"
copy_data_dir "milvus"
copy_data_dir "funasr-model-cache"
print_success "Project data directory backup completed"

# Create archive
print_info "Creating backup archive..."
cd "$BACKUP_DIR"
tar -czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME"
rm -rf "$BACKUP_NAME"
print_success "Backup archive created: ${BACKUP_NAME}.tar.gz"

# Cleanup old backups (keep last 7 days)
print_info "Cleaning up old backups..."
find "$BACKUP_DIR" -name "dwp_backup_*.tar.gz" -mtime +7 -delete
print_success "Old backups cleaned up"

print_success "Backup completed successfully: $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
