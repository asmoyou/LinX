#!/bin/bash

# LinX (灵枢) - Startup Script
# This script helps start the platform with proper initialization

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

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

# Check prerequisites
print_info "Checking prerequisites..."

if ! command -v docker >/dev/null 2>&1; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! resolve_compose_cmd; then
    print_error "Docker Compose is not installed. Please install docker compose or docker-compose first."
    exit 1
fi

print_success "Prerequisites check passed"

# Check if .env file exists
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
    print_warning ".env file not found. Creating from .env.example..."
    cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
    print_warning "Please edit .env file with your configuration before proceeding."
    print_info "Especially update these values:"
    print_info "  - POSTGRES_PASSWORD"
    print_info "  - REDIS_PASSWORD"
    print_info "  - MINIO_ROOT_PASSWORD"
    print_info "  - JWT_SECRET"
    read -p "Press Enter to continue after editing .env file..."
fi

# Parse command line arguments
MODE=${1:-all}
ENABLE_FUNASR=${ENABLE_FUNASR:-0}

is_truthy() {
    case "${1,,}" in
        1|true|yes|on)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

COMPOSE_PROFILE_ARGS=()
OPTIONAL_SERVICE_ARGS=()

if is_truthy "$ENABLE_FUNASR"; then
    COMPOSE_PROFILE_ARGS+=(--profile funasr)
    OPTIONAL_SERVICE_ARGS+=(funasr-service)
    print_info "Optional service enabled: funasr-service"
fi

print_info "Starting LinX (灵枢) in mode: $MODE"
"${SCRIPT_DIR}/prepare-data-dirs.sh"

case $MODE in
    infrastructure)
        print_info "Starting infrastructure services only..."
        run_compose up -d postgres redis minio etcd minio-milvus milvus
        ;;
    
    services)
        print_info "Starting application services only..."
        run_compose "${COMPOSE_PROFILE_ARGS[@]}" up -d api-gateway frontend "${OPTIONAL_SERVICE_ARGS[@]}"
        ;;
    
    all)
        print_info "Starting all services..."
        run_compose "${COMPOSE_PROFILE_ARGS[@]}" up -d
        ;;
    
    build)
        print_info "Building all images..."
        run_compose "${COMPOSE_PROFILE_ARGS[@]}" build
        print_success "Build completed"
        exit 0
        ;;
    
    *)
        print_error "Invalid mode: $MODE"
        print_info "Usage: $0 [infrastructure|services|all|build]"
        print_info "Optional: ENABLE_FUNASR=1 $0 [services|all|build]"
        exit 1
        ;;
esac

# Wait for services to be healthy
print_info "Waiting for services to be healthy..."
sleep 5

# Check service health
print_info "Checking service health..."

check_service() {
    local service=$1
    local port=$2
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f -s http://localhost:$port/health > /dev/null 2>&1; then
            print_success "$service is healthy"
            return 0
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            print_error "$service failed to become healthy"
            return 1
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
}

# Check infrastructure services
if [ "$MODE" = "infrastructure" ] || [ "$MODE" = "all" ]; then
    print_info "Checking infrastructure services..."
    
    # PostgreSQL
    if run_compose exec -T postgres pg_isready -U "${POSTGRES_USER:-dwp_user}" > /dev/null 2>&1; then
        print_success "PostgreSQL is ready"
    else
        print_warning "PostgreSQL is not ready yet"
    fi
    
    # Redis
    if run_compose exec -T redis redis-cli --no-auth-warning -a "${REDIS_PASSWORD:-redis_password_change_me}" ping | grep -q PONG; then
        print_success "Redis is ready"
    else
        print_warning "Redis is not ready yet"
    fi
    
    # Milvus
    if curl -f -s http://localhost:9091/healthz > /dev/null 2>&1; then
        print_success "Milvus is ready"
    else
        print_warning "Milvus is not ready yet"
    fi
    
    # MinIO
    if curl -f -s http://localhost:9000/minio/health/live > /dev/null 2>&1; then
        print_success "MinIO is ready"
    else
        print_warning "MinIO is not ready yet"
    fi
fi

# Check application services
if [ "$MODE" = "services" ] || [ "$MODE" = "all" ]; then
    print_info "Checking application services..."
    
    # API Gateway
    check_service "API Gateway" "${API_PORT:-8000}"
    
    # Frontend
    if curl -f -s "http://localhost:${FRONTEND_PORT:-3000}" > /dev/null 2>&1; then
        print_success "Frontend is ready"
    else
        print_warning "Frontend is not ready yet"
    fi

    if is_truthy "$ENABLE_FUNASR"; then
        if curl -f -s "http://localhost:${FUNASR_SERVICE_PORT:-10095}/health" > /dev/null 2>&1; then
            print_success "FunASR service is ready"
        else
            print_warning "FunASR service is not ready yet"
        fi
    fi
fi

# Print summary
echo ""
print_success "LinX (灵枢) started successfully!"
echo ""
print_info "Service URLs:"
print_info "  - Frontend: http://localhost:${FRONTEND_PORT:-3000}"
print_info "  - API Gateway: http://localhost:${API_PORT:-8000}"
if is_truthy "$ENABLE_FUNASR"; then
    print_info "  - FunASR Service: http://localhost:${FUNASR_SERVICE_PORT:-10095}"
fi
print_info "  - API Documentation: http://localhost:${API_PORT:-8000}/docs"
print_info "  - MinIO Console: http://localhost:${MINIO_CONSOLE_PORT:-9001}"
print_info "  - Milvus: localhost:${MILVUS_PORT:-19530}"
print_info "  - PostgreSQL: localhost:${POSTGRES_PORT:-5432}"
print_info "  - Redis: localhost:${REDIS_PORT:-6379}"
echo ""
print_info "To view logs:"
print_info "  docker compose logs -f [service-name]"
echo ""
print_info "To stop all services:"
print_info "  docker compose down"
echo ""
print_info "To stop and remove all data:"
print_info "  ./infrastructure/scripts/stop.sh clean"
echo ""
