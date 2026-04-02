# LinX (灵枢) - Deployment Guide

This guide covers deploying LinX (灵枢) using Docker Compose.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Configuration](#configuration)
4. [Service Architecture](#service-architecture)
5. [Network Architecture](#network-architecture)
6. [Volume Management](#volume-management)
7. [Security Considerations](#security-considerations)
8. [Monitoring and Health Checks](#monitoring-and-health-checks)
9. [Troubleshooting](#troubleshooting)
10. [Production Deployment](#production-deployment)

## Prerequisites

### System Requirements

**Minimum**:
- CPU: 8 cores
- RAM: 16 GB
- Disk: 100 GB SSD
- OS: Linux (Ubuntu 20.04+, CentOS 8+), macOS 12+, Windows 10+ with WSL2

**Recommended**:
- CPU: 16 cores
- RAM: 32 GB
- Disk: 500 GB SSD
- OS: Linux (Ubuntu 22.04 LTS)

### Software Requirements

1. **Docker**: Version 24.0+
   ```bash
   docker --version
   ```

2. **Docker Compose**: Version 2.20+
   ```bash
   docker-compose --version
   ```

3. **Git**: For cloning the repository
   ```bash
   git --version
   ```

### Installation

#### Linux (Ubuntu/Debian)
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

#### macOS
```bash
# Install Docker Desktop
# Download from: https://www.docker.com/products/docker-desktop

# Verify installation
docker --version
docker compose version
```

#### Windows (WSL2)
```bash
# Install Docker Desktop with WSL2 backend
# Download from: https://www.docker.com/products/docker-desktop

# In WSL2 terminal, verify installation
docker --version
docker compose version
```

## Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/your-org/LinX.git
cd LinX
```

### 2. Configure Environment
```bash
# Copy environment template
cp .env.example .env

# Edit configuration (IMPORTANT: Change default passwords!)
nano .env
```

**Critical settings to change**:
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `JWT_SECRET_KEY`

### 3. Start Platform
```bash
# Make scripts executable
chmod +x infrastructure/scripts/*.sh

# Start all services
./infrastructure/scripts/start.sh all
```

### 4. Verify Deployment
```bash
# Check service status
docker-compose ps

# Check logs
docker-compose logs -f api-gateway

# Access API documentation
open http://localhost:8000/docs
```

## Configuration

### Environment Variables

The platform uses environment variables for configuration. See `.env.example` for all available options.

#### Database Configuration
```bash
# PostgreSQL
POSTGRES_DB=digital_workforce
POSTGRES_USER=dwp_user
POSTGRES_PASSWORD=your_secure_password_here

# Redis
REDIS_PASSWORD=your_redis_password_here

# Milvus
MILVUS_PORT=19530
```

#### Service Ports
```bash
API_GATEWAY_PORT=8000
TASK_MANAGER_PORT=8001
AGENT_RUNTIME_PORT=8002
DOCUMENT_PROCESSOR_PORT=8003
```

#### LLM Configuration
```bash
# Local Ollama (recommended)
OLLAMA_BASE_URL=http://192.168.0.29:11434

# Or use local instance
# OLLAMA_BASE_URL=http://localhost:11434
```

#### Security
```bash
# Generate a secure JWT secret
JWT_SECRET_KEY=$(openssl rand -hex 32)

# CORS origins
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### Advanced Configuration

#### Resource Limits

Edit `docker-compose.yml` to adjust resource limits:

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
    reservations:
      cpus: '1'
      memory: 1G
```

#### Sandbox Configuration

Configure agent execution sandbox:

```bash
# Sandbox mode: auto, gvisor, firecracker, docker
SANDBOX_MODE=auto

# Resource limits for agent containers
SANDBOX_CPU_LIMIT=0.5
SANDBOX_MEMORY_LIMIT=512M
SANDBOX_TIMEOUT=30

# Optional: override sandbox runtime image (prebuilt, tool-rich)
# Recommended: use the prebuilt LinX sandbox runtime with CJK fonts and PDF tooling
# Example: linx/sandbox-runtime:py312-office
LINX_SANDBOX_PYTHON_IMAGE=linx/sandbox-runtime:py312-office

# Sandbox isolation policy (recommended)
# true = deny host subprocess fallback when sandbox is unavailable
LINX_ENFORCE_SANDBOX_ISOLATION=true
# emergency override for compatibility only
LINX_ALLOW_HOST_EXECUTION_FALLBACK=false
```

## Service Architecture

### Infrastructure Services

1. **PostgreSQL 16**: Primary database for operational data
   - Port: 5432
   - Volume: `postgres-data`
   - Health check: `pg_isready`

2. **Redis 7**: Message bus and cache
   - Port: 6379
   - Volume: `redis-data`
   - Health check: `redis-cli ping`

3. **MinIO**: Object storage (S3-compatible)
   - API Port: 9000
   - Console Port: 9001
   - Volume: `minio-data`
   - Health check: `/minio/health/live`

4. **Milvus 2.3**: Vector database for embeddings
   - Port: 19530
   - Metrics Port: 9091
   - Volume: `milvus-data`
   - Dependencies: etcd, minio-milvus
   - Health check: `/healthz`

### Application Services

1. **API Gateway**: Main entry point for all API requests
   - Port: 8000
   - Health check: `/health`
   - Dependencies: All infrastructure services

2. **Task Manager**: Goal decomposition and task orchestration
   - Port: 8001
   - Health check: `/health`
   - Dependencies: PostgreSQL, Redis, Milvus

3. **Agent Runtime**: Agent lifecycle and execution management
   - Port: 8002
   - Health check: `/health`
   - Requires: Docker socket access
   - Dependencies: All infrastructure services

4. **Document Processor**: Document ingestion and processing
   - Port: 8003
   - Health check: `/health`
   - Dependencies: PostgreSQL, Redis, Milvus, MinIO

## Network Architecture

The platform uses four isolated networks:

### 1. dwp-frontend (172.20.0.0/24)
- **Purpose**: External client access to API Gateway
- **Services**: api-gateway
- **Access**: Public

### 2. dwp-backend (172.21.0.0/24)
- **Purpose**: Internal service communication
- **Services**: All application services, Milvus
- **Access**: Internal (development: external allowed)

### 3. dwp-data (172.22.0.0/24)
- **Purpose**: Database and storage services
- **Services**: PostgreSQL, Redis, MinIO, etcd, minio-milvus
- **Access**: Internal only (isolated)

### 4. dwp-agents (172.23.0.0/24)
- **Purpose**: Agent container execution
- **Services**: agent-runtime, agent containers
- **Access**: Configurable (default: external allowed)

### Network Isolation Benefits

1. **Security**: Data services isolated from external access
2. **Performance**: Optimized routing for internal communication
3. **Scalability**: Easy to add services to appropriate networks
4. **Monitoring**: Clear network boundaries for traffic analysis

## Volume Management

### Persistent Volumes

All data is stored in Docker volumes for persistence:

```bash
# List volumes
docker volume ls | grep dwp

# Inspect volume
docker volume inspect dwp_postgres-data

# Backup volume
docker run --rm -v dwp_postgres-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres-backup.tar.gz /data

# Restore volume
docker run --rm -v dwp_postgres-data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/postgres-backup.tar.gz -C /
```

### Volume List

| Volume | Purpose | Size (Typical) |
|--------|---------|----------------|
| postgres-data | PostgreSQL database | 1-10 GB |
| redis-data | Redis persistence | 100 MB - 1 GB |
| minio-data | Object storage | 10-100 GB |
| milvus-data | Vector embeddings | 5-50 GB |
| etcd-data | Milvus metadata | 100 MB |
| minio-milvus-data | Milvus object storage | 5-50 GB |
| api-logs | API Gateway logs | 100 MB - 1 GB |
| task-manager-logs | Task Manager logs | 100 MB - 1 GB |
| agent-runtime-logs | Agent Runtime logs | 100 MB - 1 GB |
| document-processor-logs | Document Processor logs | 100 MB - 1 GB |
| document-temp | Temporary document storage | 1-10 GB |

### Backup Strategy

#### Automated Backup Script

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups/dwp-$(date +%Y%m%d-%H%M%S)"
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
docker-compose exec -T postgres pg_dump -U dwp_user digital_workforce > $BACKUP_DIR/postgres.sql

# Backup volumes
for volume in postgres-data redis-data minio-data milvus-data; do
  docker run --rm -v dwp_$volume:/data -v $BACKUP_DIR:/backup \
    alpine tar czf /backup/$volume.tar.gz /data
done

echo "Backup completed: $BACKUP_DIR"
```

## Security Considerations

### Production Security Checklist

- [ ] Change all default passwords
- [ ] Generate strong JWT secret key
- [ ] Enable TLS/SSL for all services
- [ ] Restrict network access (set `dwp-backend.internal: true`)
- [ ] Use Docker secrets for sensitive data
- [ ] Enable firewall rules
- [ ] Regular security updates
- [ ] Implement backup strategy
- [ ] Enable audit logging
- [ ] Use non-root users (already configured)
- [ ] Scan images for vulnerabilities

### TLS/SSL Configuration

For production, enable TLS:

```yaml
# Add to api-gateway service
environment:
  - ENABLE_TLS=true
  - TLS_CERT_PATH=/certs/cert.pem
  - TLS_KEY_PATH=/certs/key.pem
volumes:
  - ./certs:/certs:ro
```

### Secrets Management

Use Docker secrets for sensitive data:

```yaml
secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt

services:
  api-gateway:
    secrets:
      - postgres_password
      - jwt_secret
```

## Monitoring and Health Checks

### Health Check Endpoints

All services expose `/health` endpoints:

```bash
# Check API Gateway
curl http://localhost:8000/health

# Check Task Manager
curl http://localhost:8001/health

# Check Agent Runtime
curl http://localhost:8002/health

# Check Document Processor
curl http://localhost:8003/health
```

### Service Status

```bash
# View all service status
docker-compose ps

# View specific service logs
docker-compose logs -f api-gateway

# View resource usage
docker stats
```

### Monitoring Stack (Optional)

Add Prometheus and Grafana for monitoring:

```yaml
# Add to docker-compose.yml
prometheus:
  image: prom/prometheus:latest
  ports:
    - "9090:9090"
  volumes:
    - ./infrastructure/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus-data:/prometheus

grafana:
  image: grafana/grafana:latest
  ports:
    - "3001:3000"
  volumes:
    - grafana-data:/var/lib/grafana
```

## Troubleshooting

### Common Issues

#### 1. Services Won't Start

**Problem**: Services fail to start or crash immediately

**Solutions**:
```bash
# Check logs
docker-compose logs service-name

# Check resource usage
docker stats

# Verify configuration
docker-compose config

# Restart services
docker-compose restart service-name
```

#### 2. Database Connection Errors

**Problem**: Services can't connect to PostgreSQL

**Solutions**:
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check PostgreSQL logs
docker-compose logs postgres

# Verify connection
docker-compose exec postgres psql -U dwp_user -d digital_workforce -c "SELECT 1"

# Check network connectivity
docker-compose exec api-gateway ping postgres
```

#### 3. Out of Memory

**Problem**: Services killed due to OOM

**Solutions**:
```bash
# Check memory usage
docker stats

# Increase Docker memory limit (Docker Desktop)
# Settings > Resources > Memory

# Reduce service resource limits in docker-compose.yml
```

#### 4. Port Conflicts

**Problem**: Port already in use

**Solutions**:
```bash
# Find process using port
lsof -i :8000

# Change port in .env
API_GATEWAY_PORT=8080

# Restart services
docker-compose down
docker-compose up -d
```

#### 5. Volume Permission Issues

**Problem**: Permission denied errors

**Solutions**:
```bash
# Fix volume permissions
docker-compose down
docker volume rm dwp_volume-name
docker-compose up -d

# Or fix permissions manually
docker-compose exec service-name chown -R appuser:appuser /path
```

### Debug Mode

Enable debug logging:

```bash
# Set in .env
LOG_LEVEL=DEBUG
DEBUG=true

# Restart services
docker-compose restart
```

### Clean Restart

Complete clean restart:

```bash
# Stop and remove everything
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Rebuild and start
docker-compose build --no-cache
docker-compose up -d
```

## Production Deployment

### Pre-Production Checklist

- [ ] Review and update all environment variables
- [ ] Change all default passwords
- [ ] Configure TLS/SSL certificates
- [ ] Set up backup automation
- [ ] Configure monitoring and alerting
- [ ] Review resource limits
- [ ] Test disaster recovery procedures
- [ ] Document runbook procedures
- [ ] Set up log aggregation
- [ ] Configure firewall rules

### Production Configuration

```bash
# .env for production
ENVIRONMENT=production
LOG_LEVEL=WARNING
DEBUG=false

# Disable development features
DEV_HOT_RELOAD=false
ENABLE_API_DOCS=false

# Enable security features
ENABLE_TLS=true
ENABLE_AUDIT_LOGGING=true
```

### Scaling Considerations

For production scale, consider:

1. **Kubernetes**: Migrate to Kubernetes for better orchestration
2. **Load Balancing**: Add load balancer for API Gateway
3. **Database Replication**: Set up PostgreSQL replication
4. **Caching**: Implement Redis cluster
5. **CDN**: Use CDN for static assets
6. **Monitoring**: Implement comprehensive monitoring
7. **Backup**: Automated backup and disaster recovery

### Migration to Kubernetes

See `infrastructure/kubernetes/README.md` for Kubernetes deployment guide.

## Support

For issues and questions:
- GitHub Issues: https://github.com/your-org/LinX/issues
- Documentation: https://docs.linx.platform
- Email: support@linx.platform

## License

Copyright © 2026 灵枢科技 (LinX Technology)
