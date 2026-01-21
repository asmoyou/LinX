#!/bin/bash

# LinX (灵枢) - Backup Script
# This script creates backups of all data volumes

set -e

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

# Configuration
BACKUP_DIR=${BACKUP_DIR:-./backups}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="dwp_backup_${TIMESTAMP}"

# Create backup directory
mkdir -p "$BACKUP_DIR/$BACKUP_NAME"

print_info "Starting backup: $BACKUP_NAME"

# Backup PostgreSQL
print_info "Backing up PostgreSQL..."
docker-compose exec -T postgres pg_dumpall -U dwp_user > "$BACKUP_DIR/$BACKUP_NAME/postgres.sql"
print_success "PostgreSQL backup completed"

# Backup Redis
print_info "Backing up Redis..."
docker-compose exec -T redis redis-cli --rdb /data/dump.rdb SAVE
docker cp dwp-redis:/data/dump.rdb "$BACKUP_DIR/$BACKUP_NAME/redis.rdb"
print_success "Redis backup completed"

# Backup MinIO
print_info "Backing up MinIO..."
docker run --rm \
  --network dwp_dwp-data \
  -v "$BACKUP_DIR/$BACKUP_NAME:/backup" \
  -e MC_HOST_minio=http://minioadmin:minioadmin_change_me@minio:9000 \
  minio/mc \
  mirror minio /backup/minio
print_success "MinIO backup completed"

# Backup Milvus
print_info "Backing up Milvus..."
docker cp dwp-milvus:/var/lib/milvus "$BACKUP_DIR/$BACKUP_NAME/milvus"
print_success "Milvus backup completed"

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
