# Docker Infrastructure

This directory contains Dockerfiles for all LinX (灵枢) services.

## Dockerfiles

### 1. Dockerfile.api-gateway
**Purpose**: API Gateway service - main entry point for all API requests

**Features**:
- Multi-stage build for optimized image size
- FastAPI with Uvicorn server (4 workers)
- Health check endpoint
- Non-root user for security
- Port 8000

**Build**:
```bash
docker build -f infrastructure/docker/Dockerfile.api-gateway -t dwp-api-gateway:latest .
```

### 2. Dockerfile.task-manager
**Purpose**: Task Manager service - handles goal decomposition and task orchestration

**Features**:
- Multi-stage build
- LLM integration for task decomposition
- Health check endpoint
- Non-root user
- Port 8001

**Build**:
```bash
docker build -f infrastructure/docker/Dockerfile.task-manager -t dwp-task-manager:latest .
```

### 3. Dockerfile.agent-runtime
**Purpose**: Agent Runtime service - manages agent lifecycle and execution

**Features**:
- Multi-stage build
- Docker-in-Docker support for agent containers
- Sandbox management (gVisor/Firecracker/Docker)
- Health check endpoint
- Port 8002

**Build**:
```bash
docker build -f infrastructure/docker/Dockerfile.agent-runtime -t dwp-agent-runtime:latest .
```

**Note**: Requires access to Docker socket (`/var/run/docker.sock`) for agent containerization.

### 4. Dockerfile.document-processor
**Purpose**: Document Processor service - handles document ingestion and processing

**Features**:
- Multi-stage build
- OCR support (Tesseract)
- Audio/video processing (FFmpeg)
- PDF processing (Poppler)
- Health check endpoint
- Port 8003

**Build**:
```bash
docker build -f infrastructure/docker/Dockerfile.document-processor -t dwp-document-processor:latest .
```

## Image Optimization

All Dockerfiles use multi-stage builds to minimize image size:

1. **Builder stage**: Installs build dependencies and Python packages
2. **Final stage**: Copies only necessary files and runtime dependencies

### Size Comparison
- API Gateway: ~300MB
- Task Manager: ~300MB
- Agent Runtime: ~350MB (includes Docker client)
- Document Processor: ~500MB (includes OCR and media processing tools)

## Security Features

All images implement security best practices:

1. **Non-root user**: Services run as `appuser` (UID 1000)
2. **Minimal base image**: Using `python:3.11-slim`
3. **No unnecessary packages**: Only runtime dependencies included
4. **Health checks**: All services have health check endpoints
5. **Read-only filesystem**: Can be enforced in docker-compose

## Health Checks

All services expose a `/health` endpoint that returns:
```json
{
  "status": "healthy",
  "service": "api-gateway",
  "version": "1.0.0",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

Health checks run every 30 seconds with:
- Timeout: 10s
- Retries: 3
- Start period: 40s

## Environment Variables

Each service requires specific environment variables. See `.env.example` in the project root for complete configuration.

### Common Variables
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `MILVUS_HOST`: Milvus server hostname
- `MINIO_ENDPOINT`: MinIO server endpoint
- `OLLAMA_BASE_URL`: Ollama LLM server URL
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `ENVIRONMENT`: Deployment environment (development, staging, production)

## Building All Images

Build all images at once:
```bash
# From project root
docker-compose build
```

Or build individually:
```bash
docker-compose build api-gateway
docker-compose build task-manager
docker-compose build agent-runtime
docker-compose build document-processor
```

## Running Services

Start all services:
```bash
docker-compose up -d
```

Start specific service:
```bash
docker-compose up -d api-gateway
```

View logs:
```bash
docker-compose logs -f api-gateway
```

## Resource Limits

Default resource limits (can be adjusted in docker-compose.yml):

| Service | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|---------|-----------|--------------|--------------|-----------------|
| API Gateway | 2 cores | 2GB | 1 core | 1GB |
| Task Manager | 2 cores | 4GB | 1 core | 2GB |
| Agent Runtime | 4 cores | 8GB | 2 cores | 4GB |
| Document Processor | 2 cores | 4GB | 1 core | 2GB |

## Troubleshooting

### Build Issues

**Problem**: Build fails with "No space left on device"
```bash
# Clean up Docker
docker system prune -a
docker volume prune
```

**Problem**: Build fails with dependency errors
```bash
# Rebuild without cache
docker-compose build --no-cache
```

### Runtime Issues

**Problem**: Service fails health check
```bash
# Check service logs
docker-compose logs service-name

# Check service status
docker-compose ps
```

**Problem**: Agent Runtime can't create containers
```bash
# Verify Docker socket access
docker-compose exec agent-runtime ls -la /var/run/docker.sock

# Check Docker daemon
docker info
```

### Performance Issues

**Problem**: Services running slowly
```bash
# Check resource usage
docker stats

# Increase resource limits in docker-compose.yml
```

## Development vs Production

### Development
- Mount source code as volumes for hot reload
- Enable debug logging
- Expose all ports
- Use development database credentials

### Production
- Use built images (no volume mounts)
- Set LOG_LEVEL=WARNING or ERROR
- Restrict port exposure
- Use strong credentials
- Enable TLS/SSL
- Use secrets management
- Implement backup strategies

## Next Steps

1. Review and customize environment variables in `.env`
2. Build all images: `docker-compose build`
3. Start infrastructure services: `docker-compose up -d postgres redis minio milvus`
4. Wait for health checks to pass
5. Start application services: `docker-compose up -d`
6. Access API documentation: http://localhost:8000/docs

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
