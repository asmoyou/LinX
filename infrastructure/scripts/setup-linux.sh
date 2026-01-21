#!/bin/bash
# Platform-specific setup script for Linux
# This script installs and configures sandbox technologies for Linux

set -e

echo "=== Digital Workforce Platform - Linux Setup ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Error: Do not run this script as root${NC}"
    echo "Run as a regular user with sudo privileges"
    exit 1
fi

# Detect Linux distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
    VERSION=$VERSION_ID
    echo -e "${GREEN}Detected: $NAME $VERSION${NC}"
else
    echo -e "${RED}Error: Cannot detect Linux distribution${NC}"
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install Docker
install_docker() {
    echo ""
    echo "=== Installing Docker ==="
    
    if command_exists docker; then
        echo -e "${GREEN}Docker is already installed${NC}"
        docker --version
        return 0
    fi
    
    case $DISTRO in
        ubuntu|debian)
            # Install Docker on Ubuntu/Debian
            sudo apt-get update
            sudo apt-get install -y \
                ca-certificates \
                curl \
                gnupg \
                lsb-release
            
            # Add Docker's official GPG key
            sudo mkdir -p /etc/apt/keyrings
            curl -fsSL https://download.docker.com/linux/$DISTRO/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
            
            # Set up repository
            echo \
                "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$DISTRO \
                $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
            
            # Install Docker Engine
            sudo apt-get update
            sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
            ;;
        
        centos|rhel|fedora)
            # Install Docker on CentOS/RHEL/Fedora
            sudo yum install -y yum-utils
            sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
            sudo systemctl start docker
            sudo systemctl enable docker
            ;;
        
        *)
            echo -e "${YELLOW}Warning: Unsupported distribution for automatic Docker installation${NC}"
            echo "Please install Docker manually: https://docs.docker.com/engine/install/"
            return 1
            ;;
    esac
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    
    echo -e "${GREEN}Docker installed successfully${NC}"
    echo -e "${YELLOW}Note: You may need to log out and back in for group changes to take effect${NC}"
}

# Function to install gVisor
install_gvisor() {
    echo ""
    echo "=== Installing gVisor (runsc) ==="
    
    if command_exists runsc; then
        echo -e "${GREEN}gVisor is already installed${NC}"
        runsc --version
        return 0
    fi
    
    # Download and install runsc
    ARCH=$(uname -m)
    URL=https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}
    
    echo "Downloading runsc..."
    wget ${URL}/runsc ${URL}/runsc.sha512 -P /tmp/
    
    # Verify checksum
    cd /tmp
    sha512sum -c runsc.sha512
    
    # Install runsc
    sudo mv /tmp/runsc /usr/local/bin/
    sudo chmod +x /usr/local/bin/runsc
    
    # Clean up
    rm /tmp/runsc.sha512
    
    echo -e "${GREEN}gVisor installed successfully${NC}"
    runsc --version
    
    # Configure Docker to use gVisor
    echo ""
    echo "Configuring Docker to use gVisor runtime..."
    
    # Create or update Docker daemon.json
    DOCKER_CONFIG="/etc/docker/daemon.json"
    
    if [ ! -f "$DOCKER_CONFIG" ]; then
        sudo mkdir -p /etc/docker
        echo '{}' | sudo tee $DOCKER_CONFIG > /dev/null
    fi
    
    # Add runsc runtime to Docker config
    sudo python3 -c "
import json
import sys

config_file = '$DOCKER_CONFIG'
with open(config_file, 'r') as f:
    config = json.load(f)

if 'runtimes' not in config:
    config['runtimes'] = {}

config['runtimes']['runsc'] = {
    'path': '/usr/local/bin/runsc'
}

with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)

print('Docker configuration updated')
"
    
    # Restart Docker
    sudo systemctl restart docker
    
    echo -e "${GREEN}Docker configured to use gVisor${NC}"
    echo "Test with: docker run --runtime=runsc hello-world"
}

# Function to check KVM support
check_kvm() {
    echo ""
    echo "=== Checking KVM Support ==="
    
    if [ -e /dev/kvm ]; then
        echo -e "${GREEN}KVM is available${NC}"
        
        # Check if user has access to KVM
        if [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
            echo -e "${GREEN}User has access to KVM${NC}"
        else
            echo -e "${YELLOW}Adding user to kvm group...${NC}"
            sudo usermod -aG kvm $USER
            echo -e "${YELLOW}Note: You may need to log out and back in for group changes to take effect${NC}"
        fi
        
        return 0
    else
        echo -e "${YELLOW}KVM is not available${NC}"
        echo "Firecracker requires KVM support"
        echo "Check if virtualization is enabled in BIOS"
        return 1
    fi
}

# Function to install Firecracker
install_firecracker() {
    echo ""
    echo "=== Installing Firecracker ==="
    
    # Check KVM first
    if ! check_kvm; then
        echo -e "${YELLOW}Skipping Firecracker installation (KVM not available)${NC}"
        return 1
    fi
    
    if command_exists firecracker; then
        echo -e "${GREEN}Firecracker is already installed${NC}"
        firecracker --version
        return 0
    fi
    
    # Download and install Firecracker
    ARCH=$(uname -m)
    RELEASE_URL="https://github.com/firecracker-microvm/firecracker/releases"
    LATEST=$(basename $(curl -fsSLI -o /dev/null -w %{url_effective} ${RELEASE_URL}/latest))
    
    echo "Downloading Firecracker ${LATEST}..."
    curl -L ${RELEASE_URL}/download/${LATEST}/firecracker-${LATEST}-${ARCH}.tgz -o /tmp/firecracker.tgz
    
    # Extract and install
    cd /tmp
    tar -xzf firecracker.tgz
    sudo mv release-${LATEST}-${ARCH}/firecracker-${LATEST}-${ARCH} /usr/local/bin/firecracker
    sudo chmod +x /usr/local/bin/firecracker
    
    # Clean up
    rm -rf /tmp/firecracker.tgz /tmp/release-${LATEST}-${ARCH}
    
    echo -e "${GREEN}Firecracker installed successfully${NC}"
    firecracker --version
}

# Function to install Python dependencies
install_python_deps() {
    echo ""
    echo "=== Installing Python Dependencies ==="
    
    if ! command_exists python3; then
        echo -e "${RED}Error: Python 3 is not installed${NC}"
        echo "Please install Python 3.11 or later"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    echo "Python version: $PYTHON_VERSION"
    
    # Install pip if not available
    if ! command_exists pip3; then
        echo "Installing pip..."
        case $DISTRO in
            ubuntu|debian)
                sudo apt-get install -y python3-pip
                ;;
            centos|rhel|fedora)
                sudo yum install -y python3-pip
                ;;
        esac
    fi
    
    # Install virtualenv
    pip3 install --user virtualenv
    
    echo -e "${GREEN}Python dependencies installed${NC}"
}

# Main installation flow
main() {
    echo ""
    echo "This script will install:"
    echo "  1. Docker (if not installed)"
    echo "  2. gVisor (runsc) for enhanced security"
    echo "  3. Firecracker (if KVM is available)"
    echo "  4. Python dependencies"
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled"
        exit 0
    fi
    
    # Install components
    install_docker
    install_python_deps
    install_gvisor
    install_firecracker
    
    echo ""
    echo "=== Setup Complete ==="
    echo ""
    echo -e "${GREEN}Installation completed successfully!${NC}"
    echo ""
    echo "Installed components:"
    command_exists docker && echo "  ✓ Docker: $(docker --version)"
    command_exists runsc && echo "  ✓ gVisor: $(runsc --version)"
    command_exists firecracker && echo "  ✓ Firecracker: $(firecracker --version)"
    echo ""
    echo "Next steps:"
    echo "  1. Log out and back in (for group changes to take effect)"
    echo "  2. Run: cd backend && python3 -m venv venv && source venv/bin/activate"
    echo "  3. Run: pip install -r requirements.txt"
    echo "  4. Run: docker-compose up -d"
    echo ""
    echo "For more information, see: docs/deployment/docker-compose-deployment.md"
}

# Run main function
main
