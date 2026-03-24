#!/bin/bash

# LinX (灵枢) - Stop Script
# This script helps stop the platform gracefully

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

DATA_ROOT="${PROJECT_ROOT}/data"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse command line arguments
MODE=${1:-graceful}

print_info "Stopping LinX (灵枢)..."

if ! resolve_compose_cmd; then
    print_error "Docker Compose is not installed. Please install docker compose or docker-compose first."
    exit 1
fi

case $MODE in
    graceful)
        print_info "Stopping services gracefully (data will be preserved)..."
        run_compose stop
        print_success "All services stopped"
        ;;
    
    down)
        print_info "Stopping and removing containers (data will be preserved)..."
        run_compose down
        print_success "All containers removed"
        ;;
    
    clean)
        print_warning "This will stop services and REMOVE ALL DATA!"
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            print_info "Stopping services and removing all data..."
            run_compose down --remove-orphans
            rm -rf \
                "${DATA_ROOT}/postgres" \
                "${DATA_ROOT}/redis" \
                "${DATA_ROOT}/minio" \
                "${DATA_ROOT}/etcd" \
                "${DATA_ROOT}/minio-milvus" \
                "${DATA_ROOT}/milvus" \
                "${DATA_ROOT}/funasr-model-cache"
            "${SCRIPT_DIR}/prepare-data-dirs.sh"
            print_success "All services stopped and data removed"
        else
            print_info "Operation cancelled"
        fi
        ;;
    
    *)
        print_error "Invalid mode: $MODE"
        print_info "Usage: $0 [graceful|down|clean]"
        print_info "  graceful - Stop services (data preserved, containers remain)"
        print_info "  down     - Stop and remove containers (data preserved)"
        print_info "  clean    - Stop services and remove all data (WARNING: destructive)"
        exit 1
        ;;
esac

echo ""
print_info "To start services again:"
print_info "  ./infrastructure/scripts/start.sh"
echo ""
