# Kubernetes Deployment Guide

This guide covers deploying the Digital Workforce Management Platform to a Kubernetes cluster for production use.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Architecture Overview](#architecture-overview)
3. [Pre-Deployment Setup](#pre-deployment-setup)
4. [Deployment Steps](#deployment-steps)
5. [Configuration](#configuration)
6. [Scaling](#scaling)
7. [Monitoring](#monitoring)
8. [Backup and Recovery](#backup-and-recovery)
9. [Troubleshooting](#troubleshooting)
10. [Security Considerations](#security-considerations)

## Prerequisites

### Cluster Requirements

- **Kubernetes Version**: 1.24+
- **Nodes**: Minimum 3 nodes (recommended 5+ for production)
- **Node Resources** (per node):
  - CPU: 8+ cores
  - Memory: 32GB+ RAM
  - Storage: 200GB+ SSD
- **Storage Class**: Dynamic provisioning with SSD-backed storage
- **Ingress Controller**: NGINX Ingress Controller
- **Certificate Manager**: cert-manager (optional, for automatic TLS)

### Required Tools

```bash
# kubectl
kubectl version --client

# helm (optional, for cert-manager)
helm version

# openssl (for generating secrets)
openssl version
```

### Optional Components

- **gVisor**: For enhanced sandbox security (Linux only)
- **Prometheus**: For metrics collection
- **Grafana**: For visualization
- **Loki**: For log aggregation

## Architecture Overview

### Components

The platform consists of the following components:

**Data Layer**:
- PostgreSQL (StatefulSet) - Operational data
- Redis (StatefulSet) - Message bus and caching
- MinIO (StatefulSet) - Object storage
- Milvus (StatefulSet) - Vector database
- etcd (StatefulSet) - Milvus metadata

**Application Layer**:
- API Gateway (Deployment) - REST API and WebSocket
- Task Manager (Deployment) - Task orchestration
- Document Processor (Deployment) - Document processing
- Frontend (Deployment) - Web UI

**Networking**:
- Ingress - External access with TLS
- Services - Internal service discovery

### Resource Requirements

| Component | Replicas | CPU Request | Memory Request | Storage |
|-----------|----------|-------------|----------------|---------|
| PostgreSQL | 1 | 2 cores | 4Gi | 50Gi |
| Redis | 1 | 1 core | 2Gi | 10Gi |
| MinIO | 1 | 1 core | 2Gi | 100Gi |
| Milvus | 1 | 2 cores | 4Gi | 50Gi |
| etcd | 1 | 1 core | 2Gi | 10Gi |
| API Gateway | 2-10 | 500m | 1Gi | - |
| Task Manager | 2-10 | 1 core | 2Gi | - |
| Document Processor | 2-10 | 1 core | 2Gi | - |
| Frontend | 2-10 | 100m | 256Mi | - |

**Total Minimum**: ~12 CPU cores, ~24Gi memory, ~220Gi storage

## Pre-Deployment Setup

### 1. Install NGINX Ingress Controller

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml
```

### 2. Install cert-manager (Optional)

For automatic TLS certificate management:

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

Create ClusterIssuer for Let's Encrypt:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

### 3. Install gVisor (Optional, Linux only)

For enhanced sandbox security:

```bash
# Install runsc
wget https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/runsc
chmod +x runsc
sudo mv runsc /usr/local/bin/

# Configure containerd
sudo cat <<EOF >> /etc/containerd/config.toml
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runsc]
  runtime_type = "io.containerd.runsc.v1"
EOF

sudo systemctl restart containerd
```

### 4. Create Namespace

```bash
kubectl create namespace digital-workforce
```

### 5. Generate Secrets

Generate secure passwords and keys:

```bash
# PostgreSQL password
POSTGRES_PASSWORD=$(openssl rand -base64 32)

# Redis password
REDIS_PASSWORD=$(openssl rand -base64 32)

# MinIO credentials
MINIO_ROOT_USER="admin"
MINIO_ROOT_PASSWORD=$(openssl rand -base64 32)

# JWT secret
JWT_SECRET=$(openssl rand -base64 64)

# Encryption key (32 bytes for AES-256)
ENCRYPTION_KEY=$(openssl rand -hex 32)

# Save to file for reference
cat > secrets.env <<EOF
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
MINIO_ROOT_USER=${MINIO_ROOT_USER}
MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}
JWT_SECRET=${JWT_SECRET}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
EOF

chmod 600 secrets.env
```

### 6. Generate TLS Certificates

If not using cert-manager, generate self-signed certificates:

```bash
# Generate private key
openssl genrsa -out tls.key 2048

# Generate certificate
openssl req -new -x509 -key tls.key -out tls.crt -days 365 \
  -subj "/CN=your-domain.com"

# Create Kubernetes secret
kubectl create secret tls tls-secret \
  --cert=tls.crt \
  --key=tls.key \
  -n digital-workforce
```

## Deployment Steps

### Step 1: Update Configuration

Edit `infrastructure/kubernetes/01-configmap.yaml`:

```yaml
# Update these values:
- OLLAMA_BASE_URL: "http://your-ollama-server:11434"
- FRONTEND_URL: "https://your-domain.com"
- API_URL: "https://api.your-domain.com"
```

Edit `infrastructure/kubernetes/02-secrets.yaml`:

```bash
# Encode secrets in base64
echo -n "${POSTGRES_PASSWORD}" | base64
echo -n "${REDIS_PASSWORD}" | base64
echo -n "${MINIO_ROOT_USER}" | base64
echo -n "${MINIO_ROOT_PASSWORD}" | base64
echo -n "${JWT_SECRET}" | base64
echo -n "${ENCRYPTION_KEY}" | base64

# Update the secrets.yaml file with encoded values
```

Edit `infrastructure/kubernetes/30-ingress.yaml`:

```yaml
# Update domain names:
- hosts:
  - your-domain.com  # Replace with your domain
  - api.your-domain.com
```

### Step 2: Deploy Infrastructure Components

Deploy in order to respect dependencies:

```bash
cd infrastructure/kubernetes

# 1. Namespace and configuration
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-configmap.yaml
kubectl apply -f 02-secrets.yaml
kubectl apply -f 03-storage.yaml
kubectl apply -f 04-runtimeclass.yaml

# 2. Data layer (wait for each to be ready)
kubectl apply -f 10-postgres.yaml
kubectl wait --for=condition=ready pod -l app=postgres -n digital-workforce --timeout=300s

kubectl apply -f 11-redis.yaml
kubectl wait --for=condition=ready pod -l app=redis -n digital-workforce --timeout=300s

kubectl apply -f 12-minio.yaml
kubectl wait --for=condition=ready pod -l app=minio -n digital-workforce --timeout=300s

kubectl apply -f 13-milvus.yaml
kubectl wait --for=condition=ready pod -l app=milvus -n digital-workforce --timeout=300s

# 3. Application layer
kubectl apply -f 20-api-gateway.yaml
kubectl apply -f 21-task-manager.yaml
kubectl apply -f 22-document-processor.yaml
kubectl apply -f 23-frontend.yaml

# 4. Networking
kubectl apply -f 30-ingress.yaml
```

### Step 3: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n digital-workforce

# Check services
kubectl get svc -n digital-workforce

# Check ingress
kubectl get ingress -n digital-workforce

# Check logs
kubectl logs -f deployment/api-gateway -n digital-workforce
```

### Step 4: Initialize Database

```bash
# Run database migrations
kubectl exec -it deployment/api-gateway -n digital-workforce -- \
  alembic upgrade head
```

### Step 5: Access the Platform

Get the ingress IP:

```bash
kubectl get ingress dwp-ingress -n digital-workforce
```

Add DNS records:
- `your-domain.com` → Ingress IP
- `api.your-domain.com` → Ingress IP

Access the platform:
- Frontend: `https://your-domain.com`
- API: `https://api.your-domain.com`
- API Docs: `https://api.your-domain.com/docs`

## Configuration

### Environment Variables

All configuration is managed through ConfigMap and Secrets:

**ConfigMap** (`01-configmap.yaml`):
- Application settings
- Service URLs
- Feature flags

**Secrets** (`02-secrets.yaml`):
- Database passwords
- API keys
- Encryption keys
- JWT secrets

### Updating Configuration

```bash
# Edit ConfigMap
kubectl edit configmap app-config -n digital-workforce

# Restart pods to pick up changes
kubectl rollout restart deployment/api-gateway -n digital-workforce
kubectl rollout restart deployment/task-manager -n digital-workforce
kubectl rollout restart deployment/document-processor -n digital-workforce
```

### Resource Limits

Adjust resource limits in deployment manifests:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
  limits:
    cpu: "2000m"
    memory: "4Gi"
```

## Scaling

### Manual Scaling

```bash
# Scale API Gateway
kubectl scale deployment api-gateway --replicas=5 -n digital-workforce

# Scale Task Manager
kubectl scale deployment task-manager --replicas=3 -n digital-workforce

# Scale Document Processor
kubectl scale deployment document-processor --replicas=3 -n digital-workforce
```

### Horizontal Pod Autoscaling (HPA)

HPA is pre-configured for all application services:

```bash
# Check HPA status
kubectl get hpa -n digital-workforce

# View HPA details
kubectl describe hpa api-gateway-hpa -n digital-workforce
```

HPA configuration:
- **API Gateway**: 2-10 replicas, target 70% CPU
- **Task Manager**: 2-10 replicas, target 70% CPU
- **Document Processor**: 2-10 replicas, target 70% CPU
- **Frontend**: 2-10 replicas, target 70% CPU

### Vertical Scaling

For data layer components (PostgreSQL, Redis, Milvus):

1. Update resource requests/limits in StatefulSet
2. Delete and recreate pods (data persists in PVCs)

```bash
# Example: Scale PostgreSQL
kubectl edit statefulset postgres -n digital-workforce
# Update resources, save and exit

kubectl delete pod postgres-0 -n digital-workforce
# Pod will be recreated with new resources
```

## Monitoring

### Health Checks

All services have health check endpoints:

```bash
# API Gateway health
curl https://api.your-domain.com/health

# Check pod health
kubectl get pods -n digital-workforce
```

### Logs

```bash
# View logs
kubectl logs -f deployment/api-gateway -n digital-workforce

# View logs from all replicas
kubectl logs -f deployment/api-gateway --all-containers=true -n digital-workforce

# View logs from specific time
kubectl logs --since=1h deployment/api-gateway -n digital-workforce
```

### Metrics

If Prometheus is installed:

```bash
# Port-forward Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090:9090

# Access Prometheus UI
open http://localhost:9090
```

Key metrics to monitor:
- Pod CPU/Memory usage
- API request rate and latency
- Task completion rate
- Agent status
- Database connections
- Storage usage

### Events

```bash
# View cluster events
kubectl get events -n digital-workforce --sort-by='.lastTimestamp'

# Watch events in real-time
kubectl get events -n digital-workforce --watch
```

## Backup and Recovery

### Automated Backups

Create a CronJob for automated backups:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: backup-job
  namespace: digital-workforce
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:16
            command:
            - /bin/bash
            - -c
            - |
              pg_dump -h postgres-service -U postgres -d workforce > /backup/backup-$(date +%Y%m%d).sql
              # Upload to S3 or other backup storage
            env:
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: postgres-password
            volumeMounts:
            - name: backup
              mountPath: /backup
          volumes:
          - name: backup
            persistentVolumeClaim:
              claimName: backup-pvc
          restartPolicy: OnFailure
```

### Manual Backup

#### PostgreSQL

```bash
# Backup
kubectl exec -it postgres-0 -n digital-workforce -- \
  pg_dump -U postgres workforce > backup.sql

# Restore
kubectl exec -i postgres-0 -n digital-workforce -- \
  psql -U postgres workforce < backup.sql
```

#### Milvus

```bash
# Backup (copy data directory)
kubectl exec -it milvus-0 -n digital-workforce -- \
  tar czf /tmp/milvus-backup.tar.gz /var/lib/milvus

kubectl cp digital-workforce/milvus-0:/tmp/milvus-backup.tar.gz ./milvus-backup.tar.gz
```

#### MinIO

```bash
# Use MinIO client
kubectl run -it --rm mc --image=minio/mc --restart=Never -n digital-workforce -- \
  mc mirror minio-service/documents /backup/documents
```

### Disaster Recovery

1. **Restore PVCs**: Ensure PVCs are backed up at storage layer
2. **Restore Secrets**: Keep secrets.env file secure
3. **Restore Database**: Use pg_restore for PostgreSQL
4. **Restore Object Storage**: Sync from backup bucket
5. **Redeploy**: Apply all Kubernetes manifests

## Troubleshooting

### Common Issues

#### Pods Not Starting

```bash
# Check pod status
kubectl describe pod <pod-name> -n digital-workforce

# Check events
kubectl get events -n digital-workforce

# Common causes:
# - Insufficient resources
# - Image pull errors
# - ConfigMap/Secret not found
# - PVC not bound
```

#### Database Connection Errors

```bash
# Check PostgreSQL logs
kubectl logs -f postgres-0 -n digital-workforce

# Test connection
kubectl exec -it postgres-0 -n digital-workforce -- \
  psql -U postgres -d workforce -c "SELECT 1"

# Check service
kubectl get svc postgres-service -n digital-workforce
```

#### Ingress Not Working

```bash
# Check ingress status
kubectl describe ingress dwp-ingress -n digital-workforce

# Check ingress controller logs
kubectl logs -f -n ingress-nginx deployment/ingress-nginx-controller

# Verify DNS
nslookup your-domain.com

# Test without TLS
curl -k https://your-domain.com
```

#### High Memory Usage

```bash
# Check resource usage
kubectl top pods -n digital-workforce

# Increase memory limits
kubectl edit deployment api-gateway -n digital-workforce

# Check for memory leaks in logs
kubectl logs deployment/api-gateway -n digital-workforce | grep -i "memory\|oom"
```

#### Storage Full

```bash
# Check PVC usage
kubectl exec -it postgres-0 -n digital-workforce -- df -h

# Expand PVC (if storage class supports it)
kubectl edit pvc postgres-pvc -n digital-workforce
# Increase storage size

# Clean up old data
kubectl exec -it postgres-0 -n digital-workforce -- \
  psql -U postgres -d workforce -c "DELETE FROM audit_logs WHERE created_at < NOW() - INTERVAL '90 days'"
```

### Debug Mode

Enable debug logging:

```bash
# Update ConfigMap
kubectl edit configmap app-config -n digital-workforce
# Set LOG_LEVEL: "DEBUG"

# Restart pods
kubectl rollout restart deployment/api-gateway -n digital-workforce
```

### Support

For additional support:
- Check logs: `kubectl logs -f <pod-name> -n digital-workforce`
- Check events: `kubectl get events -n digital-workforce`
- Review documentation: `/docs`
- Contact support: support@example.com

## Security Considerations

### Network Policies

Implement network policies to restrict traffic:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-gateway-policy
  namespace: digital-workforce
spec:
  podSelector:
    matchLabels:
      app: api-gateway
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
```

### Pod Security Standards

Apply Pod Security Standards:

```bash
kubectl label namespace digital-workforce \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted
```

### RBAC

Create service accounts with minimal permissions:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: api-gateway-sa
  namespace: digital-workforce
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: api-gateway-role
  namespace: digital-workforce
rules:
- apiGroups: [""]
  resources: ["configmaps", "secrets"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: api-gateway-binding
  namespace: digital-workforce
subjects:
- kind: ServiceAccount
  name: api-gateway-sa
roleRef:
  kind: Role
  name: api-gateway-role
  apiGroup: rbac.authorization.k8s.io
```

### Secrets Management

Consider using external secrets management:

- **HashiCorp Vault**: For centralized secrets
- **AWS Secrets Manager**: For AWS deployments
- **Azure Key Vault**: For Azure deployments
- **Google Secret Manager**: For GCP deployments

### Image Security

- Use specific image tags (not `latest`)
- Scan images for vulnerabilities (Trivy, Snyk)
- Use private container registry
- Sign images with Cosign

### TLS/SSL

- Use cert-manager for automatic certificate renewal
- Enforce TLS 1.2+ only
- Use strong cipher suites
- Enable HSTS headers

## Performance Tuning

### Database Optimization

```sql
-- PostgreSQL tuning
ALTER SYSTEM SET shared_buffers = '4GB';
ALTER SYSTEM SET effective_cache_size = '12GB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET work_mem = '64MB';
ALTER SYSTEM SET min_wal_size = '1GB';
ALTER SYSTEM SET max_wal_size = '4GB';
```

### Milvus Optimization

```yaml
# Adjust index parameters for better performance
# In Milvus configuration
indexType: IVF_FLAT
nlist: 1024
nprobe: 16
```

### Application Tuning

- Enable connection pooling
- Implement caching (Redis)
- Use async I/O
- Optimize database queries
- Enable compression

## Maintenance

### Rolling Updates

```bash
# Update image
kubectl set image deployment/api-gateway \
  api-gateway=your-registry/api-gateway:v2.0.0 \
  -n digital-workforce

# Monitor rollout
kubectl rollout status deployment/api-gateway -n digital-workforce

# Rollback if needed
kubectl rollout undo deployment/api-gateway -n digital-workforce
```

### Certificate Renewal

If using cert-manager, certificates renew automatically. For manual certificates:

```bash
# Generate new certificate
openssl req -new -x509 -key tls.key -out tls.crt -days 365

# Update secret
kubectl create secret tls tls-secret \
  --cert=tls.crt \
  --key=tls.key \
  -n digital-workforce \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart ingress controller
kubectl rollout restart deployment ingress-nginx-controller -n ingress-nginx
```

### Cleanup

```bash
# Remove old ReplicaSets
kubectl delete replicaset -l app=api-gateway -n digital-workforce \
  --field-selector status.replicas=0

# Clean up completed jobs
kubectl delete job -n digital-workforce --field-selector status.successful=1

# Clean up old pods
kubectl delete pod -n digital-workforce --field-selector status.phase=Succeeded
```

## Conclusion

This guide covers the essential aspects of deploying and managing the Digital Workforce Management Platform on Kubernetes. For additional information, refer to:

- [Docker Compose Deployment](./docker-compose-deployment.md)
- [API Documentation](../api/)
- [Architecture Documentation](../architecture/)
- [Troubleshooting Guide](../troubleshooting.md)

For production deployments, ensure you:
- ✅ Use proper secrets management
- ✅ Enable monitoring and alerting
- ✅ Implement backup and disaster recovery
- ✅ Apply security best practices
- ✅ Test thoroughly in staging environment
- ✅ Have runbooks for common operations
- ✅ Plan for scaling and capacity
