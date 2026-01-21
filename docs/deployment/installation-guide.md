# Installation Guide

This guide provides step-by-step instructions for installing LinX (灵枢) on Linux, macOS, and Windows.

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Linux Installation](#linux-installation)
3. [macOS Installation](#macos-installation)
4. [Windows Installation](#windows-installation)
5. [Post-Installation Setup](#post-installation-setup)
6. [Verification](#verification)
7. [Troubleshooting](#troubleshooting)

## System Requirements

### Minimum Requirements

- **CPU**: 4 cores
- **RAM**: 8GB
- **Storage**: 50GB free space
- **OS**: 
  - Linux: Ubuntu 20.04+, Debian 11+, CentOS 8+, RHEL 8+, Fedora 35+
  - macOS: 12.0 (Monterey) or later
  - Windows: Windows 10/11 with WSL 2

### Recommended Requirements

- **CPU**: 8+ cores
- **RAM**: 16GB+
- **Storage**: 100GB+ SSD
- **Network**: Stable internet connection

### Software Prerequisites

- **Python**: 3.11 or later
- **Node.js**: 20.x or later (for frontend development)
- **Docker**: 24.0 or later
- **Docker Compose**: 2.20 or later

## Linux Installation

### Automated Installation (Recommended)

We provide an automated setup script for Linux:

```bash
# Download the repository
git clone https://github.com/your-org/linx.git
cd linx

# Run the setup script
chmod +x infrastructure/scripts/setup-linux.sh
./infrastructure/scripts/setup-linux.sh
```

The script will:
- Install Docker and Docker Compose
- Install gVisor (for enhanced security)
- Install Firecracker (if KVM is available)
- Install Python 3.11+ and dependencies
- Configure user permissions

### Manual Installation

#### 1. Install Docker

**Ubuntu/Debian**:
```bash
# Update package index
sudo apt-get update

# Install dependencies
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER
```

**CentOS/RHEL/Fedora**:
```bash
# Install Docker
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Start Docker
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group
sudo usermod -aG docker $USER
```

#### 2. Install Python 3.11+

**Ubuntu/Debian**:
```bash
sudo apt-get install -y python3.11 python3.11-venv python3-pip
```

**CentOS/RHEL/Fedora**:
```bash
sudo yum install -y python3.11 python3-pip
```

#### 3. Install gVisor (Optional, for enhanced security)

```bash
# Download runsc
ARCH=$(uname -m)
URL=https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}
wget ${URL}/runsc ${URL}/runsc.sha512

# Verify and install
sha512sum -c runsc.sha512
sudo mv runsc /usr/local/bin/
sudo chmod +x /usr/local/bin/runsc

# Configure Docker to use gVisor
sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "runtimes": {
    "runsc": {
      "path": "/usr/local/bin/runsc"
    }
  }
}
EOF

# Restart Docker
sudo systemctl restart docker
```

#### 4. Clone Repository and Setup

```bash
# Clone repository
git clone https://github.com/your-org/linx.git
cd linx

# Create Python virtual environment
cd backend
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Configure environment
cd ..
cp .env.example .env
# Edit .env with your configuration
nano .env
```

#### 5. Start Services

```bash
# Start infrastructure services
docker-compose up -d

# Wait for services to be ready
sleep 30

# Run database migrations
cd backend
source venv/bin/activate
alembic upgrade head
```

## macOS Installation

### Automated Installation (Recommended)

```bash
# Download the repository
git clone https://github.com/your-org/linx.git
cd linx

# Run the setup script
chmod +x infrastructure/scripts/setup-macos.sh
./infrastructure/scripts/setup-macos.sh
```

The script will:
- Install Homebrew (if not installed)
- Install Docker Desktop
- Install Python 3.11+
- Install PostgreSQL and Redis clients
- Install Python dependencies

### Manual Installation

#### 1. Install Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### 2. Install Docker Desktop

```bash
brew install --cask docker
```

Start Docker Desktop from Applications folder.

#### 3. Install Python 3.11+

```bash
brew install python@3.11
brew link python@3.11
```

#### 4. Install Database Clients

```bash
brew install postgresql@16 redis
```

#### 5. Clone Repository and Setup

```bash
# Clone repository
git clone https://github.com/your-org/linx.git
cd linx

# Create Python virtual environment
cd backend
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Configure environment
cd ..
cp .env.example .env
# Edit .env with your configuration
nano .env
```

#### 6. Start Services

```bash
# Ensure Docker Desktop is running

# Start infrastructure services
docker-compose up -d

# Wait for services to be ready
sleep 30

# Run database migrations
cd backend
source venv/bin/activate
alembic upgrade head
```

## Windows Installation

### Automated Installation (Recommended)

Open PowerShell as Administrator:

```powershell
# Download the repository
git clone https://github.com/your-org/linx.git
cd linx

# Run the setup script
.\infrastructure\scripts\setup-windows.ps1
```

The script will:
- Install Chocolatey package manager
- Install WSL 2
- Install Docker Desktop
- Install Python 3.11+
- Install Git
- Install Python dependencies

**Note**: You will need to restart your computer after installation.

### Manual Installation

#### 1. Install WSL 2

Open PowerShell as Administrator:

```powershell
# Enable WSL
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart

# Enable Virtual Machine Platform
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# Restart computer
Restart-Computer

# After restart, set WSL 2 as default
wsl --set-default-version 2

# Install Ubuntu from Microsoft Store
# Or use: wsl --install -d Ubuntu
```

#### 2. Install Docker Desktop

Download and install Docker Desktop from:
https://www.docker.com/products/docker-desktop

Ensure "Use WSL 2 based engine" is enabled in Docker Desktop settings.

#### 3. Install Python 3.11+

Download and install Python from:
https://www.python.org/downloads/

Ensure "Add Python to PATH" is checked during installation.

#### 4. Install Git

Download and install Git from:
https://git-scm.com/download/win

#### 5. Clone Repository and Setup

Open PowerShell:

```powershell
# Clone repository
git clone https://github.com/your-org/linx.git
cd linx

# Create Python virtual environment
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install Python dependencies
pip install -r requirements.txt

# Configure environment
cd ..
copy .env.example .env
# Edit .env with your configuration
notepad .env
```

#### 6. Start Services

```powershell
# Ensure Docker Desktop is running

# Start infrastructure services
docker-compose up -d

# Wait for services to be ready
Start-Sleep -Seconds 30

# Run database migrations
cd backend
.\venv\Scripts\Activate.ps1
alembic upgrade head
```

## Post-Installation Setup

### 1. Configure Environment Variables

Edit the `.env` file with your configuration:

```bash
# Database
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/workforce

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=your_access_key
MINIO_SECRET_KEY=your_secret_key

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530

# LLM Provider (Ollama)
OLLAMA_BASE_URL=http://localhost:11434

# JWT Secret
JWT_SECRET=your_jwt_secret_here

# Encryption Key (32 bytes for AES-256)
ENCRYPTION_KEY=your_encryption_key_here
```

### 2. Initialize Database

```bash
cd backend
source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1

# Run migrations
alembic upgrade head

# Create admin user (optional)
python -c "
from database.connection import get_db_session
from access_control.models import User
from access_control.rbac import Role

with get_db_session() as session:
    admin = User(
        username='admin',
        email='admin@example.com',
        role=Role.ADMIN.value
    )
    admin.set_password('admin123')  # Change this!
    session.add(admin)
    session.commit()
    print('Admin user created')
"
```

### 3. Install Ollama (Local LLM)

**Linux**:
```bash
curl https://ollama.ai/install.sh | sh
ollama pull llama2
```

**macOS**:
```bash
brew install ollama
ollama pull llama2
```

**Windows**:
Download from https://ollama.ai/download

### 4. Start Application Services

```bash
# Start API Gateway
cd backend
source venv/bin/activate
uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000

# In another terminal, start frontend (for development)
cd frontend
npm install
npm run dev
```

## Verification

### 1. Check Services

```bash
# Check Docker containers
docker ps

# Expected containers:
# - postgres
# - redis
# - minio
# - milvus
# - etcd
```

### 2. Test API

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","version":"1.0.0"}
```

### 3. Test Frontend

Open browser and navigate to:
- Development: http://localhost:5173
- Production: http://localhost:80

### 4. Test Database Connection

```bash
cd backend
source venv/bin/activate
python -c "
from database.connection import get_db_session
with get_db_session() as session:
    result = session.execute('SELECT 1')
    print('Database connection successful')
"
```

### 5. Test Ollama

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "llama2",
  "prompt": "Hello, world!"
}'
```

## Troubleshooting

### Docker Issues

**Problem**: Docker daemon not running
```bash
# Linux
sudo systemctl start docker
sudo systemctl status docker

# macOS/Windows
# Start Docker Desktop from Applications
```

**Problem**: Permission denied
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in for changes to take effect
```

### Database Issues

**Problem**: Cannot connect to PostgreSQL
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check logs
docker logs postgres

# Restart PostgreSQL
docker-compose restart postgres
```

**Problem**: Migration fails
```bash
# Reset database (WARNING: This will delete all data)
docker-compose down -v
docker-compose up -d
cd backend
alembic upgrade head
```

### Python Issues

**Problem**: Module not found
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # Linux/macOS
.\venv\Scripts\Activate.ps1  # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

**Problem**: Python version mismatch
```bash
# Check Python version
python --version

# Should be 3.11 or later
# If not, install correct version and recreate venv
```

### Port Conflicts

**Problem**: Port already in use
```bash
# Find process using port
lsof -i :8000  # Linux/macOS
netstat -ano | findstr :8000  # Windows

# Kill process or change port in configuration
```

### Ollama Issues

**Problem**: Ollama not responding
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
# Linux: sudo systemctl restart ollama
# macOS: brew services restart ollama
# Windows: Restart Ollama from Start Menu
```

## Next Steps

After successful installation:

1. **Configure LLM Providers**: See [Configuration Guide](../backend/configuration-validation.md)
2. **Set Up Users**: Create user accounts and assign roles
3. **Deploy Agents**: Create and deploy AI agents
4. **Upload Knowledge**: Upload documents to knowledge base
5. **Submit Tasks**: Start submitting goals and tasks

## Additional Resources

- [Docker Compose Deployment](./docker-compose-deployment.md)
- [Kubernetes Deployment](./kubernetes-deployment.md)
- [Configuration Guide](../backend/configuration-validation.md)
- [User Manual](../user-guide/user-manual.md)
- [Troubleshooting Guide](./troubleshooting-guide.md)

## Support

For installation issues:
- Check [Troubleshooting Guide](./troubleshooting-guide.md)
- Review logs: `docker-compose logs`
- Open an issue on GitHub
- Contact support: support@example.com
