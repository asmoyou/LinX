# Docker Compose Deployment Guide

This guide covers deploying LinX (灵枢) using Docker Compose for development and staging environments.

## Prerequisites

- Docker 20.10 or later
- Docker Compose 2.0 or later
- At least 8GB RAM
- At least 50GB disk space

## Quick Start

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd digital-workforce-platform
   ```

2. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start the platform**:
   ```bash
   chmod +x infrastructure/scripts/start.sh
   ./infrastructure/scripts/start.sh all
   ```

4. **Access the platform**:
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - MinIO Console: http://localhost:9001

## Architecture

The Docker Compose setup includes the following services:

### Infrastructure Services
- **PostgreSQL**: Primary database for operational data
- **Redis**: Message bus and caching
- **Milvus**: Vector database for embeddings
- **MinIO**: Object storage for files
- **etcd**: Milvus metadata storage

### Application Services
- **API Gateway**: FastAPI REST API and WebSocket server
- **Task Manager**: Task decomposition and coordination
- **Document Processor**: Document processing worker
- **Frontend**: React web application

## Configuration

### Environment Variables

Key environment variables in `.env`:

```bash
# Database
POSTGRES_PASSWORD=your_secure_password
REDIS_PASSWORD=your_secure_password
MINIO_ROOT_PASSWORD=your_secure_password

# Security
JWT_SECRET_KEY=your_long_random_string

# LLM Providers
OLLAMA_BASE_URL=http://localhost:11434
OPENAI_API_KEY=your_key_here  # Optional
```

### Volume Management

Data is persisted in Docker volumes:
- `postgres-data`: PostgreSQL database
- `redis-data`: Redis persistence
- `minio-data`: MinIO object storage
- `milvus-data`: Milvus vector database
- `etcd-data`: etcd metadata

## Service Management

### Start Services

```bash
# Start all services
./infrastructure/scripts/start.sh all

# Start infrastructure only
./infrastructure/scripts/start.sh infrastructure

# Start application services only
./infrastructure/scripts/start.sh services

# Build images
./infrastructure/scripts/start.sh build
```

### Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes all data)
docker-compose down -v
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

### Restart Service

```bash
docker-compose restart api-gateway
```

## Health Checks

All services include health checks. Check service health:

```bash
# Check all services
docker-compose ps

# Check specific service
docker-compose ps api-gateway

# View health check logs
docker inspect dwp-api-gateway | grep -A 10 Health
```

## Backup and Restore

### Create Backup

```bash
chmod +x infrastructure/scripts/backup.sh
./infrastructure/scripts/backup.sh
```

Backups are stored in `./backups/` directory.

### Restore from Backup

```bash
# Stop services
docker-compose down

# Extract backup
cd backups
tar -xzf dwp_backup_YYYYMMDD_HHMMSS.tar.gz

# Restore PostgreSQL
docker-compose up -d postgres
cat dwp_backup_YYYYMMDD_HHMMSS/postgres.sql | docker-compose exec -T postgres psql -U dwp_user

# Restore Redis
docker cp dwp_backup_YYYYMMDD_HHMMSS/redis.rdb dwp-redis:/data/dump.rdb
docker-compose restart redis

# Restore MinIO
docker run --rm \
  --network dwp_dwp-data \
  -v $(pwd)/dwp_backup_YYYYMMDD_HHMMSS/minio:/backup \
  -e MC_HOST_minio=http://minioadmin:password@minio:9000 \
  minio/mc \
  mirror /backup minio

# Restore Milvus
docker cp dwp_backup_YYYYMMDD_HHMMSS/milvus dwp-milvus:/var/lib/

# Start all services
docker-compose up -d
```

## Troubleshooting

### Service Won't Start

1. Check logs:
   ```bash
   docker-compose logs service-name
   ```

2. Check health:
   ```bash
   docker-compose ps
   ```

3. Restart service:
   ```bash
   docker-compose restart service-name
   ```

### Database Connection Issues

1. Verify PostgreSQL is running:
   ```bash
   docker-compose exec postgres pg_isready -U dwp_user
   ```

2. Check connection from API:
   ```bash
   docker-compose exec api-gateway python -c "from database.connection import get_db_session; print('OK')"
   ```

### Out of Memory

1. Check resource usage:
   ```bash
   docker stats
   ```

2. Increase Docker memory limit in Docker Desktop settings

3. Reduce service resource limits in docker-compose.yml

### Port Conflicts

If ports are already in use, update in `.env`:

```bash
API_PORT=8001
FRONTEND_PORT=3001
POSTGRES_PORT=5433
```

## Performance Tuning

### PostgreSQL

Edit `docker-compose.yml` to add:

```yaml
postgres:
  command:
    - "postgres"
    - "-c"
    - "max_connections=200"
    - "-c"
    - "shared_buffers=256MB"
```

### Redis

Adjust memory limit:

```yaml
redis:
  command: >
    redis-server
    --maxmemory 1gb
    --maxmemory-policy allkeys-lru
```

### Milvus

For better performance, use SSD for Milvus data volume.

## Security Considerations

1. **Change default passwords** in `.env`
2. **Use strong JWT secret** (at least 32 characters)
3. **Enable TLS** for production (see Kubernetes deployment guide)
4. **Restrict network access** using Docker networks
5. **Regular backups** using the backup script
6. **Update images** regularly for security patches

## Monitoring

### View Metrics

- Milvus metrics: http://localhost:9091/metrics
- API metrics: http://localhost:8000/metrics

### Resource Usage

```bash
# Real-time stats
docker stats

# Disk usage
docker system df
```

## Upgrading

1. **Backup data**:
   ```bash
   ./infrastructure/scripts/backup.sh
   ```

2. **Pull latest images**:
   ```bash
   docker-compose pull
   ```

3. **Rebuild custom images**:
   ```bash
   docker-compose build
   ```

4. **Restart services**:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

5. **Run migrations**:
   ```bash
   docker-compose exec api-gateway alembic upgrade head
   ```

## Next Steps

- For production deployment, see [Kubernetes Deployment Guide](./kubernetes-deployment.md)
- For monitoring setup, see [Monitoring Guide](./monitoring-setup.md)
- For security hardening, see [Security Guide](./security-best-practices.md)
