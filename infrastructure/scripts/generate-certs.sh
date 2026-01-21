#!/bin/bash
# Generate TLS certificates for LinX (灵枢)
# Usage: ./generate-certs.sh [development|production]

set -e

MODE=${1:-development}
CERTS_DIR="infrastructure/certs"
DAYS_VALID=365

if [ "$MODE" = "production" ]; then
    DAYS_VALID=730
fi

echo "Generating certificates for $MODE environment (valid for $DAYS_VALID days)..."

# Create certs directory
mkdir -p "$CERTS_DIR"
cd "$CERTS_DIR"

# Generate CA
echo "Generating Certificate Authority..."
openssl genrsa -out ca-key.pem 4096
openssl req -new -x509 -days $DAYS_VALID -key ca-key.pem -out ca-cert.pem \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=LinX-CA"

# Generate server certificate
echo "Generating server certificate..."
openssl genrsa -out server-key.pem 4096
openssl req -new -key server-key.pem -out server-csr.pem \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

# Create extensions file for SAN
cat > server-ext.cnf <<EOF
subjectAltName = @alt_names
[alt_names]
DNS.1 = localhost
DNS.2 = api-gateway
DNS.3 = postgres
DNS.4 = milvus
DNS.5 = minio
DNS.6 = redis
IP.1 = 127.0.0.1
EOF

openssl x509 -req -days $DAYS_VALID -in server-csr.pem \
    -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial \
    -out server-cert.pem -extfile server-ext.cnf

# Generate client certificate
echo "Generating client certificate..."
openssl genrsa -out client-key.pem 4096
openssl req -new -key client-key.pem -out client-csr.pem \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=client"
openssl x509 -req -days $DAYS_VALID -in client-csr.pem \
    -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial \
    -out client-cert.pem

# Set permissions
chmod 600 *-key.pem
chmod 644 *-cert.pem

# Clean up CSR files
rm -f *.csr.pem *.cnf *.srl

echo "Certificates generated successfully in $CERTS_DIR/"
echo ""
echo "Files created:"
echo "  - ca-cert.pem (Certificate Authority)"
echo "  - ca-key.pem (CA Private Key)"
echo "  - server-cert.pem (Server Certificate)"
echo "  - server-key.pem (Server Private Key)"
echo "  - client-cert.pem (Client Certificate)"
echo "  - client-key.pem (Client Private Key)"
echo ""
echo "⚠️  IMPORTANT: Keep *-key.pem files secure and never commit to version control!"

if [ "$MODE" = "production" ]; then
    echo ""
    echo "📝 For production, consider using:"
    echo "  - Let's Encrypt for public-facing services"
    echo "  - Your organization's CA for internal services"
    echo "  - Hardware Security Module (HSM) for key storage"
fi
