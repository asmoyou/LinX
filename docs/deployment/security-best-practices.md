# Security Best Practices

Security guidelines for deploying and operating the Digital Workforce Management Platform.

## Table of Contents

1. [Authentication and Authorization](#authentication-and-authorization)
2. [Data Protection](#data-protection)
3. [Network Security](#network-security)
4. [Container Security](#container-security)
5. [Secrets Management](#secrets-management)
6. [Monitoring and Auditing](#monitoring-and-auditing)
7. [Incident Response](#incident-response)

## Authentication and Authorization

### Password Policy

**Requirements**:
- Minimum 12 characters
- Mix of uppercase, lowercase, numbers, symbols
- No common passwords
- Change every 90 days
- No password reuse (last 5 passwords)

**Implementation**:
```python
# In access_control/models.py
PASSWORD_MIN_LENGTH = 12
PASSWORD_REQUIRE_UPPERCASE = True
PASSWORD_REQUIRE_LOWERCASE = True
PASSWORD_REQUIRE_DIGITS = True
PASSWORD_REQUIRE_SYMBOLS = True
```

### Multi-Factor Authentication (MFA)

**Recommendation**: Enable MFA for all users, especially admins.

**Implementation**:
- Use TOTP (Time-based One-Time Password)
- Backup codes for recovery
- SMS as fallback (less secure)

### JWT Token Security

**Best Practices**:
- Short expiration (1 hour for access tokens)
- Longer expiration for refresh tokens (7 days)
- Rotate secrets regularly
- Use strong signing algorithm (HS256 or RS256)
- Store tokens securely (httpOnly cookies)

**Configuration**:
```bash
# .env
JWT_SECRET=<strong-random-secret>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
```

### Role-Based Access Control (RBAC)

**Principle of Least Privilege**:
- Grant minimum necessary permissions
- Regular access reviews
- Remove unused accounts
- Separate admin and user accounts

**Roles**:
- **Admin**: Full system access (use sparingly)
- **Manager**: User and agent management
- **User**: Create agents and tasks
- **Viewer**: Read-only access

## Data Protection

### Encryption at Rest

**Database Encryption**:
```bash
# PostgreSQL TDE
# Enable in postgresql.conf
ssl = on
ssl_cert_file = '/path/to/server.crt'
ssl_key_file = '/path/to/server.key'
```

**File Encryption**:
```bash
# MinIO server-side encryption
MINIO_KMS_SECRET_KEY=<encryption-key>
```

**Disk Encryption**:
- Use LUKS (Linux)
- Use FileVault (macOS)
- Use BitLocker (Windows)

### Encryption in Transit

**TLS/SSL**:
- Use TLS 1.2 or higher
- Strong cipher suites only
- Valid certificates (not self-signed in production)
- HSTS headers

**Configuration**:
```nginx
# nginx.conf
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers HIGH:!aNULL:!MD5;
ssl_prefer_server_ciphers on;
add_header Strict-Transport-Security "max-age=31536000" always;
```

### Data Classification

**Levels**:
- **Public**: No restrictions
- **Internal**: Authenticated users only
- **Confidential**: Specific users/roles
- **Restricted**: Admin only

**Implementation**:
```python
from shared.data_classification import classify_data

classification = classify_data(content)
# Returns: PUBLIC, INTERNAL, CONFIDENTIAL, or RESTRICTED
```

### Data Retention

**Policy**:
- Audit logs: 1 year
- Task history: 90 days
- User data: Until account deletion
- Backups: 30 days

**Implementation**:
```python
# Automated cleanup
from shared.data_retention import cleanup_old_data

cleanup_old_data(
    table='audit_logs',
    retention_days=365
)
```

## Network Security

### Firewall Configuration

**Recommended Rules**:
```bash
# Allow HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Deny direct database access
ufw deny 5432/tcp
ufw deny 6379/tcp
ufw deny 9000/tcp

# Allow SSH (with key-based auth only)
ufw allow 22/tcp

# Enable firewall
ufw enable
```

### Network Segmentation

**Architecture**:
```
Internet
    ↓
[Load Balancer]
    ↓
[Frontend Network] ← Frontend
    ↓
[Backend Network] ← API Gateway, Task Manager
    ↓
[Data Network] ← PostgreSQL, Redis, MinIO, Milvus
    ↓
[Agent Network] ← Agent Runtime (isolated)
```

### API Security

**Best Practices**:
- Rate limiting (100 req/min default)
- Input validation
- Output encoding
- CORS configuration
- API versioning

**Configuration**:
```python
# api_gateway/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

## Container Security

### Image Security

**Best Practices**:
- Use official base images
- Scan images for vulnerabilities
- Use specific tags (not `latest`)
- Multi-stage builds
- Minimal images (Alpine, Distroless)

**Scanning**:
```bash
# Scan with Trivy
trivy image api-gateway:latest

# Scan with Snyk
snyk container test api-gateway:latest
```

### Runtime Security

**gVisor** (Linux only):
```bash
# Run with gVisor
docker run --runtime=runsc api-gateway:latest
```

**Resource Limits**:
```yaml
# docker-compose.yml
services:
  api-gateway:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

**Security Options**:
```yaml
services:
  api-gateway:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
```

### Kubernetes Security

**Pod Security Standards**:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: digital-workforce
  labels:
    pod-security.kubernetes.io/enforce: restricted
```

**Network Policies**:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-gateway-policy
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
```

## Secrets Management

### Environment Variables

**Never commit secrets to Git**:
```bash
# .gitignore
.env
*.key
*.pem
secrets/
```

**Use Secret Management**:
- HashiCorp Vault
- AWS Secrets Manager
- Azure Key Vault
- Google Secret Manager

### Kubernetes Secrets

```bash
# Create secret
kubectl create secret generic app-secrets \
  --from-literal=jwt-secret=<secret> \
  --from-literal=db-password=<password> \
  -n digital-workforce

# Use in pod
env:
- name: JWT_SECRET
  valueFrom:
    secretKeyRef:
      name: app-secrets
      key: jwt-secret
```

### Secret Rotation

**Schedule**:
- JWT secrets: Every 90 days
- Database passwords: Every 180 days
- API keys: Every 90 days
- TLS certificates: Before expiration

## Monitoring and Auditing

### Audit Logging

**What to Log**:
- Authentication attempts
- Authorization failures
- Data access
- Configuration changes
- Admin actions
- Security events

**Implementation**:
```python
from access_control.audit_logger import log_audit_event

log_audit_event(
    user_id=user.id,
    action="document_access",
    resource_type="document",
    resource_id=doc.id,
    result="success"
)
```

### Security Monitoring

**Metrics to Monitor**:
- Failed login attempts
- Unusual API activity
- Resource usage spikes
- Error rates
- Unauthorized access attempts

**Alerting**:
```yaml
# Prometheus alert rules
groups:
- name: security
  rules:
  - alert: HighFailedLogins
    expr: rate(failed_logins[5m]) > 10
    annotations:
      summary: "High rate of failed logins"
```

### Log Analysis

**Tools**:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Loki + Grafana
- Splunk
- CloudWatch Logs

**Retention**:
- Security logs: 1 year minimum
- Audit logs: Per compliance requirements
- Application logs: 90 days

## Incident Response

### Preparation

**Incident Response Plan**:
1. Detection
2. Containment
3. Eradication
4. Recovery
5. Lessons Learned

**Team Roles**:
- Incident Commander
- Technical Lead
- Communications Lead
- Documentation Lead

### Detection

**Indicators of Compromise**:
- Unusual login patterns
- Unexpected data access
- Configuration changes
- Resource usage spikes
- Failed authentication attempts

### Response Steps

**1. Detect and Assess**:
```bash
# Check recent logins
docker exec postgres psql -U postgres -d workforce -c "
SELECT * FROM audit_logs
WHERE action = 'login'
ORDER BY created_at DESC
LIMIT 100;
"

# Check failed attempts
grep "authentication failed" /var/log/api-gateway.log
```

**2. Contain**:
```bash
# Disable compromised account
docker exec postgres psql -U postgres -d workforce -c "
UPDATE users SET is_active = false WHERE id = 'user-123';
"

# Block IP address
ufw deny from <ip-address>
```

**3. Eradicate**:
- Remove malware
- Patch vulnerabilities
- Close security gaps

**4. Recover**:
```bash
# Restore from backup
./infrastructure/scripts/restore.sh

# Rotate all secrets
# Reset all passwords
# Verify system integrity
```

**5. Document**:
- Timeline of events
- Actions taken
- Root cause
- Lessons learned
- Preventive measures

## Compliance

### GDPR

**Requirements**:
- Data protection by design
- Right to access
- Right to erasure
- Data portability
- Breach notification (72 hours)

**Implementation**:
```python
# User data export
from access_control.gdpr import export_user_data

data = export_user_data(user_id)

# User data deletion
from access_control.gdpr import delete_user_data

delete_user_data(user_id)
```

### SOC 2

**Controls**:
- Access controls
- Encryption
- Monitoring
- Incident response
- Change management

### HIPAA (if applicable)

**Requirements**:
- PHI encryption
- Access controls
- Audit trails
- Business associate agreements

## Security Checklist

### Deployment

- [ ] Change default passwords
- [ ] Enable TLS/SSL
- [ ] Configure firewall
- [ ] Set up monitoring
- [ ] Enable audit logging
- [ ] Configure backups
- [ ] Test disaster recovery
- [ ] Security scan images
- [ ] Review access controls
- [ ] Document security procedures

### Operations

- [ ] Regular security updates
- [ ] Vulnerability scanning
- [ ] Access reviews
- [ ] Log analysis
- [ ] Backup verification
- [ ] Incident drills
- [ ] Security training
- [ ] Compliance audits

## Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [Docker Security](https://docs.docker.com/engine/security/)
- [Kubernetes Security](https://kubernetes.io/docs/concepts/security/)

## Support

For security issues:
- **Security Team**: security@example.com
- **Emergency**: +1-555-SECURITY
- **Bug Bounty**: https://bugcrowd.com/your-org
