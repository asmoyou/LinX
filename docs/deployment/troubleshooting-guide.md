# Troubleshooting Guide

Common issues and solutions for LinX (灵枢).

## Table of Contents

1. [Installation Issues](#installation-issues)
2. [Docker Issues](#docker-issues)
3. [Database Issues](#database-issues)
4. [API Issues](#api-issues)
5. [Agent Issues](#agent-issues)
6. [Performance Issues](#performance-issues)
7. [Security Issues](#security-issues)

## Installation Issues

### Python Version Mismatch

**Problem**: `python: command not found` or wrong version

**Solution**:
```bash
# Check Python version
python3 --version

# Install Python 3.11+
# Ubuntu/Debian
sudo apt-get install python3.11

# macOS
brew install python@3.11

# Windows
# Download from python.org
```

### Docker Not Running

**Problem**: `Cannot connect to Docker daemon`

**Solution**:
```bash
# Linux
sudo systemctl start docker
sudo systemctl enable docker

# macOS/Windows
# Start Docker Desktop from Applications
```

### Permission Denied

**Problem**: `Permission denied` when running Docker

**Solution**:
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in
# Or run: newgrp docker
```

## Docker Issues

### Container Won't Start

**Problem**: Container exits immediately

**Solution**:
```bash
# Check logs
docker logs <container-name>

# Check container status
docker ps -a

# Restart container
docker-compose restart <service-name>
```

### Port Already in Use

**Problem**: `Port is already allocated`

**Solution**:
```bash
# Find process using port
lsof -i :8000  # Linux/macOS
netstat -ano | findstr :8000  # Windows

# Kill process or change port in docker-compose.yml
```

### Out of Disk Space

**Problem**: `no space left on device`

**Solution**:
```bash
# Clean up Docker
docker system prune -a
docker volume prune

# Remove old images
docker image prune -a

# Check disk usage
df -h
```

## Database Issues

### Cannot Connect to PostgreSQL

**Problem**: `Connection refused` or `timeout`

**Solution**:
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check logs
docker logs postgres

# Restart PostgreSQL
docker-compose restart postgres

# Test connection
docker exec postgres psql -U postgres -c "SELECT 1"
```

### Migration Fails

**Problem**: `alembic upgrade head` fails

**Solution**:
```bash
# Check current version
cd backend
alembic current

# Check migration history
alembic history

# Downgrade and retry
alembic downgrade -1
alembic upgrade head

# If still fails, check logs
alembic upgrade head --sql > migration.sql
# Review migration.sql for issues
```

### Database Locked

**Problem**: `database is locked`

**Solution**:
```bash
# Check active connections
docker exec postgres psql -U postgres -d workforce -c "
SELECT pid, usename, application_name, state
FROM pg_stat_activity
WHERE datname = 'workforce';
"

# Terminate connections
docker exec postgres psql -U postgres -d workforce -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'workforce' AND pid <> pg_backend_pid();
"
```

## API Issues

### API Not Responding

**Problem**: API returns 502/504 or times out

**Solution**:
```bash
# Check API logs
docker logs api-gateway

# Check if API is running
curl http://localhost:8000/health

# Restart API
docker-compose restart api-gateway

# Check resource usage
docker stats api-gateway
```

### Authentication Fails

**Problem**: `401 Unauthorized` or `Invalid token`

**Solution**:
```bash
# Check JWT secret is set
echo $JWT_SECRET

# Verify token expiration
# Tokens expire after 1 hour by default

# Re-login to get new token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user","password":"pass"}'
```

### Rate Limit Exceeded

**Problem**: `429 Too Many Requests`

**Solution**:
- Wait for rate limit to reset (check `X-RateLimit-Reset` header)
- Reduce request frequency
- Contact admin to increase rate limit

## Agent Issues

### Agent Won't Start

**Problem**: Agent status stuck in "idle"

**Solution**:
```bash
# Check agent logs
docker logs agent-runtime

# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
# Linux: sudo systemctl restart ollama
# macOS: brew services restart ollama

# Check agent configuration
# Verify skills are available
# Check resource limits
```

### Agent Crashes

**Problem**: Agent terminates unexpectedly

**Solution**:
```bash
# Check logs for errors
docker logs agent-runtime

# Check resource usage
docker stats agent-runtime

# Increase resource limits in docker-compose.yml
# Check for memory leaks
# Review agent code for errors
```

### Task Stuck in "Pending"

**Problem**: Task never starts

**Solution**:
- Check if agents are available
- Verify agent has required skills
- Check task queue: `docker logs task-manager`
- Check resource quotas
- Restart task manager: `docker-compose restart task-manager`

## Performance Issues

### Slow Response Times

**Problem**: API responses are slow

**Solution**:
```bash
# Check resource usage
docker stats

# Check database performance
docker exec postgres psql -U postgres -d workforce -c "
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
"

# Enable query caching
# Optimize database indexes
# Scale horizontally (add more instances)
```

### High Memory Usage

**Problem**: System running out of memory

**Solution**:
```bash
# Check memory usage
free -h
docker stats

# Identify memory hogs
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}"

# Increase memory limits
# Restart services
# Consider upgrading hardware
```

### Disk Space Issues

**Problem**: Running out of disk space

**Solution**:
```bash
# Check disk usage
df -h
du -sh /var/lib/docker

# Clean up Docker
docker system prune -a -f
docker volume prune -f

# Clean up logs
find /var/log -name "*.log" -mtime +7 -delete

# Archive old data
# Increase disk space
```

## Security Issues

### Suspected Breach

**Problem**: Unusual activity detected

**Actions**:
1. **Isolate**: Disconnect affected systems
2. **Investigate**: Check logs for suspicious activity
3. **Rotate**: Change all passwords and API keys
4. **Patch**: Update all systems
5. **Monitor**: Enable enhanced logging
6. **Report**: Contact security team

### SSL/TLS Errors

**Problem**: Certificate errors

**Solution**:
```bash
# Check certificate expiration
openssl x509 -in cert.pem -noout -dates

# Renew certificate
# Update certificate in configuration
# Restart services
```

## Getting Help

### Collect Diagnostic Information

```bash
# System information
uname -a
docker version
docker-compose version

# Service status
docker ps -a
docker-compose ps

# Logs
docker-compose logs > logs.txt

# Resource usage
docker stats --no-stream > stats.txt
```

### Contact Support

Include the following when reporting issues:
- Error messages
- Steps to reproduce
- System information
- Logs
- Screenshots (if applicable)

**Support Channels**:
- Email: support@example.com
- GitHub Issues: https://github.com/your-org/linx/issues
- Discord: https://discord.gg/linx
- Emergency: +1-555-0123

## Additional Resources

- [Installation Guide](./installation-guide.md)
- [Administrator Guide](../user-guide/administrator-guide.md)
- [API Documentation](../api/api-documentation.md)
- [FAQ](../user-guide/faq.md)
