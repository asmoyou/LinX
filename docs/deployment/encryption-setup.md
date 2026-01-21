# Data Encryption Setup Guide

Complete guide for configuring encryption at rest and in transit for LinX (灵枢).

## Overview

This guide covers:
- PostgreSQL encryption configuration
- Milvus data file encryption
- MinIO server-side encryption
- TLS/SSL for all communications
- Key management

## Encryption at Rest

### PostgreSQL Encryption

#### Option 1: Transparent Data Encryption (TDE) - Enterprise

For PostgreSQL Enterprise Edition with TDE support:

```bash
# Enable TDE in postgresql.conf
data_encryption = on
encryption_key_command = '/path/to/key/retrieval/script'

# Restart PostgreSQL
sudo systemctl restart postgresql
```

#### Option 2: Disk-Level Encryption (Recommended for Open Source)

Using LUKS on Linux:

```bash
# Create encrypted volume
sudo cryptsetup luksFormat /dev/sdb
sudo cryptsetup luksOpen /dev/sdb pgdata_encrypted

# Format and mount
sudo mkfs.ext4 /dev/mapper/pgdata_encrypted
sudo mount /dev/mapper/pgdata_encrypted /var/lib/postgresql/data

# Configure auto-mount in /etc/crypttab
pgdata_encrypted /dev/sdb none luks
```

Using FileVault on macOS:

```bash
# Enable FileVault for PostgreSQL data directory
sudo fdesetup enable
```

Using BitLocker on Windows:

```powershell
# Enable BitLocker for PostgreSQL data drive
Enable-BitLocker -MountPoint "D:" -EncryptionMethod Aes256
```

### Milvus Data File Encryption

Milvus doesn't have built-in encryption, so we use filesystem-level encryption:

```bash
# Linux: Use LUKS for Milvus data directory
sudo cryptsetup luksFormat /dev/sdc
sudo cryptsetup luksOpen /dev/sdc milvus_encrypted
sudo mkfs.ext4 /dev/mapper/milvus_encrypted
sudo mount /dev/mapper/milvus_encrypted /var/lib/milvus

# macOS: Use encrypted APFS volume
diskutil apfs addVolume disk1 APFS MilvusData -encryption
```

Configure in `docker-compose.yml`:

```yaml
milvus:
  volumes:
    - /encrypted/milvus/data:/var/lib/milvus
```

### MinIO Server-Side Encryption (SSE)

#### SSE-S3 (MinIO Managed Keys)

Configure in MinIO:

```bash
# Set encryption environment variables
export MINIO_KMS_SECRET_KEY="my-minio-key:CHANGEME32BYTESLONGSECRETKEY"

# Start MinIO with encryption
minio server /data --console-address ":9001"
```

In `docker-compose.yml`:

```yaml
minio:
  environment:
    - MINIO_KMS_SECRET_KEY=my-minio-key:${MINIO_ENCRYPTION_KEY}
```

#### SSE-KMS (External Key Management)

For production with external KMS (AWS KMS, HashiCorp Vault):

```bash
# Configure MinIO to use external KMS
export MINIO_KMS_KES_ENDPOINT=https://kes-server:7373
export MINIO_KMS_KES_KEY_NAME=my-minio-key
export MINIO_KMS_KES_CERT_FILE=/path/to/client.cert
export MINIO_KMS_KES_KEY_FILE=/path/to/client.key
export MINIO_KMS_KES_CA_PATH=/path/to/ca.cert
```

Enable default encryption for buckets:

```python
# In backend/object_storage/minio_client.py
from minio import Minio
from minio.commonconfig import ENABLED
from minio.sse import SseS3

# Enable encryption for bucket
client.set_bucket_encryption(
    "documents",
    SseS3()
)
```

## Encryption in Transit (TLS/SSL)

### Generate TLS Certificates

For development (self-signed):

```bash
# Create CA
openssl genrsa -out ca-key.pem 4096
openssl req -new -x509 -days 365 -key ca-key.pem -out ca-cert.pem

# Create server certificate
openssl genrsa -out server-key.pem 4096
openssl req -new -key server-key.pem -out server-csr.pem
openssl x509 -req -days 365 -in server-csr.pem -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial -out server-cert.pem

# Store certificates
mkdir -p infrastructure/certs
mv *.pem infrastructure/certs/
chmod 600 infrastructure/certs/*-key.pem
```

For production, use Let's Encrypt or your organization's CA.

### API Gateway TLS Configuration

Update `backend/api_gateway/main.py`:

```python
import uvicorn
from fastapi import FastAPI

app = FastAPI()

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8443,
        ssl_keyfile="infrastructure/certs/server-key.pem",
        ssl_certfile="infrastructure/certs/server-cert.pem",
        ssl_ca_certs="infrastructure/certs/ca-cert.pem",
    )
```

In `docker-compose.yml`:

```yaml
api-gateway:
  ports:
    - "8443:8443"
  volumes:
    - ./infrastructure/certs:/certs:ro
  environment:
    - SSL_KEYFILE=/certs/server-key.pem
    - SSL_CERTFILE=/certs/server-cert.pem
```

### PostgreSQL TLS Configuration

Configure in `postgresql.conf`:

```conf
ssl = on
ssl_cert_file = '/certs/server-cert.pem'
ssl_key_file = '/certs/server-key.pem'
ssl_ca_file = '/certs/ca-cert.pem'
ssl_ciphers = 'HIGH:MEDIUM:+3DES:!aNULL'
ssl_prefer_server_ciphers = on
ssl_min_protocol_version = 'TLSv1.2'
```

Update connection string in `backend/database/connection.py`:

```python
DATABASE_URL = (
    f"postgresql://{user}:{password}@{host}:{port}/{database}"
    f"?sslmode=require&sslcert=/certs/client-cert.pem"
    f"&sslkey=/certs/client-key.pem&sslrootcert=/certs/ca-cert.pem"
)
```

### Milvus TLS Configuration

Configure in `milvus.yaml`:

```yaml
proxy:
  tls:
    enabled: true
    certFile: /certs/server-cert.pem
    keyFile: /certs/server-key.pem
    caFile: /certs/ca-cert.pem
```

Update client connection in `backend/memory_system/milvus_connection.py`:

```python
from pymilvus import connections

connections.connect(
    alias="default",
    host="milvus",
    port="19530",
    secure=True,
    server_pem_path="/certs/ca-cert.pem",
    client_pem_path="/certs/client-cert.pem",
    client_key_path="/certs/client-key.pem",
)
```

### MinIO TLS Configuration

Configure MinIO with TLS:

```bash
# Place certificates in MinIO certs directory
mkdir -p ~/.minio/certs
cp server-cert.pem ~/.minio/certs/public.crt
cp server-key.pem ~/.minio/certs/private.key
cp ca-cert.pem ~/.minio/certs/CAs/

# MinIO will automatically use TLS
minio server /data
```

Update client in `backend/object_storage/minio_client.py`:

```python
from minio import Minio

client = Minio(
    "minio:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=True,  # Enable TLS
    cert_check=True,
)
```

### Redis TLS Configuration

Configure in `redis.conf`:

```conf
tls-port 6380
port 0
tls-cert-file /certs/server-cert.pem
tls-key-file /certs/server-key.pem
tls-ca-cert-file /certs/ca-cert.pem
tls-auth-clients no
```

Update client in `backend/message_bus/redis_manager.py`:

```python
import redis

client = redis.Redis(
    host="redis",
    port=6380,
    ssl=True,
    ssl_certfile="/certs/client-cert.pem",
    ssl_keyfile="/certs/client-key.pem",
    ssl_ca_certs="/certs/ca-cert.pem",
)
```

## Key Management

### Environment Variables

Store encryption keys securely:

```bash
# .env file (never commit to git)
POSTGRES_ENCRYPTION_KEY=<base64-encoded-key>
MINIO_ENCRYPTION_KEY=<32-byte-key>
JWT_SECRET_KEY=<random-secret>
```

### External Key Management Service (Production)

#### HashiCorp Vault Integration

```python
# backend/shared/key_management.py
import hvac

class KeyManager:
    def __init__(self):
        self.client = hvac.Client(url='https://vault:8200')
        self.client.token = os.getenv('VAULT_TOKEN')
    
    def get_encryption_key(self, key_name: str) -> str:
        secret = self.client.secrets.kv.v2.read_secret_version(
            path=f'encryption/{key_name}'
        )
        return secret['data']['data']['key']
```

#### AWS KMS Integration

```python
import boto3

class AWSKeyManager:
    def __init__(self):
        self.kms = boto3.client('kms')
    
    def encrypt_data(self, data: bytes, key_id: str) -> bytes:
        response = self.kms.encrypt(
            KeyId=key_id,
            Plaintext=data
        )
        return response['CiphertextBlob']
    
    def decrypt_data(self, encrypted_data: bytes) -> bytes:
        response = self.kms.decrypt(
            CiphertextBlob=encrypted_data
        )
        return response['Plaintext']
```

## Docker Compose Configuration

Complete `docker-compose.yml` with encryption:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    volumes:
      - /encrypted/postgres/data:/var/lib/postgresql/data
      - ./infrastructure/certs:/certs:ro
    environment:
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    command: >
      postgres
      -c ssl=on
      -c ssl_cert_file=/certs/server-cert.pem
      -c ssl_key_file=/certs/server-key.pem
      -c ssl_ca_file=/certs/ca-cert.pem

  milvus:
    image: milvusdb/milvus:latest
    volumes:
      - /encrypted/milvus/data:/var/lib/milvus
      - ./infrastructure/certs:/certs:ro
      - ./milvus.yaml:/milvus/configs/milvus.yaml

  minio:
    image: minio/minio:latest
    volumes:
      - /encrypted/minio/data:/data
      - ./infrastructure/certs:/certs:ro
    environment:
      - MINIO_ROOT_USER=${MINIO_ROOT_USER}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}
      - MINIO_KMS_SECRET_KEY=${MINIO_ENCRYPTION_KEY}
    command: server /data --console-address ":9001" --certs-dir /certs

  redis:
    image: redis:7
    volumes:
      - ./infrastructure/certs:/certs:ro
    command: >
      redis-server
      --tls-port 6380
      --port 0
      --tls-cert-file /certs/server-cert.pem
      --tls-key-file /certs/server-key.pem
      --tls-ca-cert-file /certs/ca-cert.pem

  api-gateway:
    build: ./backend
    ports:
      - "8443:8443"
    volumes:
      - ./infrastructure/certs:/certs:ro
    environment:
      - SSL_KEYFILE=/certs/server-key.pem
      - SSL_CERTFILE=/certs/server-cert.pem
      - DATABASE_URL=postgresql://user:pass@postgres:5432/db?sslmode=require
```

## Verification

### Test PostgreSQL TLS

```bash
psql "postgresql://user:pass@localhost:5432/db?sslmode=require" -c "SHOW ssl;"
```

### Test MinIO Encryption

```python
from minio import Minio

client = Minio("localhost:9000", secure=True)
# Upload will be automatically encrypted
client.fput_object("documents", "test.txt", "/tmp/test.txt")
```

### Test API TLS

```bash
curl -k https://localhost:8443/health
```

### Verify Encryption Status

```bash
# Check PostgreSQL encryption
psql -c "SELECT name, setting FROM pg_settings WHERE name LIKE '%ssl%';"

# Check MinIO encryption
mc admin info myminio

# Check Redis TLS
redis-cli --tls --cert /certs/client-cert.pem --key /certs/client-key.pem ping
```

## Security Best Practices

1. **Certificate Management**
   - Use strong key sizes (4096-bit RSA or 256-bit ECC)
   - Rotate certificates annually
   - Use separate certificates for each service
   - Store private keys with restricted permissions (600)

2. **Key Storage**
   - Never commit keys to version control
   - Use environment variables or secret management
   - Rotate encryption keys regularly
   - Use hardware security modules (HSM) for production

3. **TLS Configuration**
   - Enforce TLS 1.2 or higher
   - Disable weak ciphers
   - Enable perfect forward secrecy
   - Use HSTS headers for web endpoints

4. **Monitoring**
   - Log all encryption/decryption operations
   - Monitor certificate expiration
   - Alert on TLS handshake failures
   - Audit key access

## Troubleshooting

### Certificate Issues

```bash
# Verify certificate
openssl x509 -in server-cert.pem -text -noout

# Test TLS connection
openssl s_client -connect localhost:8443 -CAfile ca-cert.pem
```

### Permission Issues

```bash
# Fix certificate permissions
chmod 600 infrastructure/certs/*-key.pem
chmod 644 infrastructure/certs/*-cert.pem
chown postgres:postgres /certs/*
```

### Connection Issues

```bash
# Check if TLS is enabled
netstat -tlnp | grep 8443

# Test database connection
psql "postgresql://user:pass@localhost:5432/db?sslmode=require&sslrootcert=/certs/ca-cert.pem"
```

## References

- [PostgreSQL SSL Documentation](https://www.postgresql.org/docs/current/ssl-tcp.html)
- [MinIO Encryption Guide](https://min.io/docs/minio/linux/operations/server-side-encryption.html)
- [Redis TLS Documentation](https://redis.io/docs/management/security/encryption/)
- [FastAPI HTTPS Documentation](https://fastapi.tiangolo.com/deployment/https/)
