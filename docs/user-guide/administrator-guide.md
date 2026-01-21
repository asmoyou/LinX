# Administrator Guide

This guide is for system administrators managing LinX (灵枢).

## Table of Contents

1. [User Management](#user-management)
2. [System Configuration](#system-configuration)
3. [Resource Management](#resource-management)
4. [Monitoring](#monitoring)
5. [Backup and Recovery](#backup-and-recovery)
6. [Security](#security)
7. [Maintenance](#maintenance)

## User Management

### Creating Users

```python
from database.connection import get_db_session
from access_control.models import User
from access_control.rbac import Role

with get_db_session() as session:
    user = User(
        username='john.doe',
        email='john@example.com',
        role=Role.USER.value
    )
    user.set_password('secure_password')
    session.add(user)
    session.commit()
```

### User Roles

- **Admin**: Full system access
- **Manager**: Manage users and agents
- **User**: Create agents and tasks
- **Viewer**: Read-only access

### Managing Quotas

```python
from database.connection import get_db_session
from shared.resource_quotas import ResourceQuota

with get_db_session() as session:
    quota = ResourceQuota(
        user_id='user-123',
        max_agents=10,
        max_storage_gb=100,
        max_cpu_cores=8,
        max_memory_gb=16
    )
    session.add(quota)
    session.commit()
```

## System Configuration

### Environment Variables

Key configuration in `.env`:

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/workforce

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=password

# Security
JWT_SECRET=your-secret-key
ENCRYPTION_KEY=your-encryption-key

# LLM
OLLAMA_BASE_URL=http://localhost:11434
```

### Configuration File

Edit `backend/config.yaml` for advanced settings.

## Resource Management

### Monitoring Resource Usage

```bash
# Check Docker resource usage
docker stats

# Check disk usage
df -h

# Check database size
psql -U postgres -d workforce -c "SELECT pg_size_pretty(pg_database_size('workforce'));"
```

### Setting Resource Limits

Edit `docker-compose.yml`:

```yaml
services:
  api-gateway:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

## Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Database health
docker exec postgres pg_isready

# Redis health
docker exec redis redis-cli ping
```

### Logs

```bash
# View all logs
docker-compose logs -f

# View specific service
docker-compose logs -f api-gateway

# View last 100 lines
docker-compose logs --tail=100 api-gateway
```

### Metrics

Access Prometheus metrics at:
- API Gateway: `http://localhost:8000/metrics`
- Grafana Dashboard: `http://localhost:3000`

## Backup and Recovery

### Database Backup

```bash
# Backup PostgreSQL
docker exec postgres pg_dump -U postgres workforce > backup.sql

# Restore
docker exec -i postgres psql -U postgres workforce < backup.sql
```

### MinIO Backup

```bash
# Backup MinIO data
docker exec minio mc mirror /data /backup
```

### Full System Backup

```bash
# Run backup script
./infrastructure/scripts/backup.sh
```

## Security

### SSL/TLS Configuration

Configure TLS in `nginx.conf` or Ingress.

### Firewall Rules

```bash
# Allow only necessary ports
ufw allow 80/tcp
ufw allow 443/tcp
ufw deny 5432/tcp  # PostgreSQL (internal only)
ufw deny 6379/tcp  # Redis (internal only)
```

### Security Scanning

```bash
# Scan for vulnerabilities
docker scan api-gateway:latest

# Check for secrets
trufflehog filesystem .
```

## Maintenance

### Updating the Platform

```bash
# Pull latest changes
git pull origin main

# Rebuild images
docker-compose build

# Restart services
docker-compose up -d
```

### Database Migrations

```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

### Cleaning Up

```bash
# Remove old Docker images
docker image prune -a

# Clean up logs
find /var/log -name "*.log" -mtime +30 -delete

# Vacuum database
docker exec postgres psql -U postgres -d workforce -c "VACUUM ANALYZE;"
```

## Troubleshooting

See [Troubleshooting Guide](../deployment/troubleshooting-guide.md) for common issues.

## Support

For administrator support:
- Email: admin-support@example.com
- Documentation: https://docs.your-domain.com
- Emergency: +1-555-0123
