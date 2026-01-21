# Quick Start Guide

Get LinX (灵枢) running in 5 minutes!

## Prerequisites

- Docker 24.0+
- Docker Compose 2.20+
- 16GB RAM minimum
- 100GB disk space

## Installation Steps

### 1. Clone and Configure

```bash
# Clone repository
git clone https://github.com/your-org/LinX.git
cd LinX

# Copy environment file
cp .env.example .env

# Edit .env and change these values:
# - POSTGRES_PASSWORD
# - REDIS_PASSWORD
# - MINIO_ROOT_PASSWORD
# - JWT_SECRET_KEY
nano .env
```

### 2. Start Services

```bash
# Make scripts executable
chmod +x infrastructure/scripts/*.sh

# Start all services
./infrastructure/scripts/start.sh all
```

This will:
- Pull all required Docker images
- Start infrastructure services (PostgreSQL, Redis, MinIO, Milvus)
- Start application services (API Gateway, Task Manager, Agent Runtime, Document Processor)
- Wait for all health checks to pass

### 3. Verify Installation

```bash
# Check service status
docker-compose ps

# All services should show "healthy" status
```

### 4. Access Services

- **API Documentation**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001 (admin/minioadmin)
- **API Gateway**: http://localhost:8000
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **Milvus**: localhost:19530

## Quick Commands

### Start Services
```bash
# Start all services
./infrastructure/scripts/start.sh all

# Start only infrastructure
./infrastructure/scripts/start.sh infrastructure

# Start only application services
./infrastructure/scripts/start.sh services
```

### Stop Services
```bash
# Stop gracefully (data preserved)
./infrastructure/scripts/stop.sh graceful

# Stop and remove containers (data preserved)
./infrastructure/scripts/stop.sh down

# Stop and remove all data (WARNING: destructive)
./infrastructure/scripts/stop.sh clean
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api-gateway

# Last 100 lines
docker-compose logs --tail=100 api-gateway
```

### Check Status
```bash
# Service status
docker-compose ps

# Resource usage
docker stats

# Health checks
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

### Restart Services
```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart api-gateway
```

## Testing the Platform

### 1. Check API Documentation

Open http://localhost:8000/docs in your browser to see the interactive API documentation.

### 2. Create a Test User (Coming Soon)

```bash
# Using the API
curl -X POST http://localhost:8000/api/v1/users/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "testpassword123"
  }'
```

### 3. Upload a Document (Coming Soon)

```bash
# Upload a test document
curl -X POST http://localhost:8000/api/v1/knowledge/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@test.pdf"
```

## Troubleshooting

### Services Won't Start

```bash
# Check logs
docker-compose logs

# Check Docker resources
docker system df

# Clean up if needed
docker system prune -a
```

### Port Conflicts

```bash
# Find what's using the port
lsof -i :8000

# Change port in .env
API_GATEWAY_PORT=8080

# Restart
docker-compose down
docker-compose up -d
```

### Out of Memory

```bash
# Check memory usage
docker stats

# Increase Docker memory limit in Docker Desktop:
# Settings > Resources > Memory > 16GB
```

### Database Connection Issues

```bash
# Check PostgreSQL
docker-compose exec postgres psql -U dwp_user -d digital_workforce -c "SELECT 1"

# Check network
docker-compose exec api-gateway ping postgres
```

## Next Steps

1. **Read the Full Documentation**: See `infrastructure/DEPLOYMENT.md`
2. **Configure LLM Provider**: Set up Ollama or configure cloud LLM
3. **Create Your First Agent**: Use the API to create an agent
4. **Submit a Goal**: Test the task decomposition system
5. **Upload Documents**: Build your knowledge base

## Common Tasks

### Backup Data

```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U dwp_user digital_workforce > backup.sql

# Backup all volumes
docker run --rm -v dwp_postgres-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres-backup.tar.gz /data
```

### Update Services

```bash
# Pull latest images
docker-compose pull

# Rebuild services
docker-compose build

# Restart with new images
docker-compose up -d
```

### View Service Metrics

```bash
# Resource usage
docker stats

# Disk usage
docker system df

# Network info
docker network ls
docker network inspect dwp_dwp-backend
```

## Getting Help

- **Documentation**: `infrastructure/DEPLOYMENT.md`
- **Docker Guide**: `infrastructure/docker/README.md`
- **GitHub Issues**: https://github.com/your-org/LinX/issues
- **API Docs**: http://localhost:8000/docs (when running)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      API Gateway (8000)                      │
│                   FastAPI + WebSocket                        │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
┌───────▼────────┐ ┌────▼────────┐ ┌────▼────────────┐
│ Task Manager   │ │Agent Runtime│ │Document Processor│
│    (8001)      │ │   (8002)    │ │     (8003)      │
└───────┬────────┘ └────┬────────┘ └────┬────────────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼────┐  ┌───────▼────┐  ┌──────▼─────┐
│ PostgreSQL │  │   Milvus   │  │   MinIO    │
│   (5432)   │  │  (19530)   │  │  (9000)    │
└────────────┘  └────────────┘  └────────────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
                  ┌─────▼─────┐
                  │   Redis   │
                  │   (6379)  │
                  └───────────┘
```

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| API Gateway | 8000 | Main API endpoint |
| Task Manager | 8001 | Task orchestration |
| Agent Runtime | 8002 | Agent management |
| Document Processor | 8003 | Document processing |
| PostgreSQL | 5432 | Primary database |
| Redis | 6379 | Message bus & cache |
| MinIO API | 9000 | Object storage |
| MinIO Console | 9001 | Web UI |
| Milvus | 19530 | Vector database |
| Milvus Metrics | 9091 | Metrics endpoint |

## Resource Requirements

### Minimum
- CPU: 8 cores
- RAM: 16 GB
- Disk: 100 GB SSD

### Recommended
- CPU: 16 cores
- RAM: 32 GB
- Disk: 500 GB SSD

### Per Service (Default Limits)

| Service | CPU | Memory |
|---------|-----|--------|
| PostgreSQL | 2 cores | 2 GB |
| Redis | 1 core | 1 GB |
| MinIO | 2 cores | 2 GB |
| Milvus | 4 cores | 8 GB |
| API Gateway | 2 cores | 2 GB |
| Task Manager | 2 cores | 4 GB |
| Agent Runtime | 4 cores | 8 GB |
| Document Processor | 2 cores | 4 GB |

**Total**: ~19 cores, ~31 GB RAM

## Support

Need help? Check:
1. Service logs: `docker-compose logs -f service-name`
2. Health status: `docker-compose ps`
3. Full documentation: `infrastructure/DEPLOYMENT.md`
4. GitHub Issues: Report bugs and request features

---

**Ready to build with LinX!** 🚀
