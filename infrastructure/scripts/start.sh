#!/bin/bash

# Digital Workforce Platform - Startup Script
# This script helps start the platform with proper initialization

set -e

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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
print_info "Checking prerequisites..."

if ! command_exists docker; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command_exists docker-compose; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

print_success "Prerequisites check passed"

# Check if .env file exists
if [ ! -f .env ]; then
    print_warning ".env file not found. Creating from .env.example..."
    cp .env.example .env
    print_warning "Please edit .env file with your configuration before proceeding."
    print_info "Especially update these values:"
    print_info "  - POSTGRES_PASSWORD"
    print_info "  - REDIS_PASSWORD"
    print_info "  - MINIO_ROOT_PASSWORD"
    print_info "  - JWT_SECRET_KEY"
    read -p "Press Enter to continue after editing .env file..."
fi

# Parse command line arguments
MODE=${1:-all}

print_info "Starting Digital Workforce Platform in mode: $MODE"

case $MODE in
    infrastructure)
        print_info "Starting infrastructure services only..."
        docker-compose up -d postgres redis minio etcd minio-milvus milvus
        ;;
    
    services)
        print_info "Starting application services only..."
        docker-compose up -d api-gateway task-manager document-processor frontend
        ;;
    
    all)
        print_info "Starting all services..."
        docker-compose up -d
        ;;
    
    build)
        print_info "Building all images..."
        docker-compose build
        print_success "Build completed"
        exit 0
        ;;
    
    *)
        print_error "Invalid mode: $MODE"
        print_info "Usage: $0 [infrastructure|services|all|build]"
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
    if docker-compose exec -T postgres pg_isready -U dwp_user > /dev/null 2>&1; then
        print_success "PostgreSQL is ready"
    else
        print_warning "PostgreSQL is not ready yet"
    fi
    
    # Redis
    if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
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
    check_service "API Gateway" 8000
    
    # Frontend
    if curl -f -s http://localhost:3000/health > /dev/null 2>&1; then
        print_success "Frontend is ready"
    else
        print_warning "Frontend is not ready yet"
    fi
fi

# Print summary
echo ""
print_success "Digital Workforce Platform started successfully!"
echo ""
print_info "Service URLs:"
print_info "  - Frontend: http://localhost:3000"
print_info "  - API Gateway: http://localhost:8000"
print_info "  - API Documentation: http://localhost:8000/docs"
print_info "  - MinIO Console: http://localhost:9001"
print_info "  - Milvus: localhost:19530"
print_info "  - PostgreSQL: localhost:5432"
print_info "  - Redis: localhost:6379"
echo ""
print_info "To view logs:"
print_info "  docker-compose logs -f [service-name]"
echo ""
print_info "To stop all services:"
print_info "  docker-compose down"
echo ""
print_info "To stop and remove all data:"
print_info "  docker-compose down -v"
echo ""
