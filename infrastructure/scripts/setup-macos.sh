#!/bin/bash
# Platform-specific setup script for macOS
# This script installs and configures required components for macOS

set -e

echo "=== Digital Workforce Platform - macOS Setup ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on macOS
if [ "$(uname)" != "Darwin" ]; then
    echo -e "${RED}Error: This script is for macOS only${NC}"
    exit 1
fi

# Get macOS version
MACOS_VERSION=$(sw_vers -productVersion)
echo -e "${GREEN}Detected: macOS $MACOS_VERSION${NC}"

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install Homebrew
install_homebrew() {
    echo ""
    echo "=== Installing Homebrew ==="
    
    if command_exists brew; then
        echo -e "${GREEN}Homebrew is already installed${NC}"
        brew --version
        return 0
    fi
    
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add Homebrew to PATH for Apple Silicon Macs
    if [ -f /opt/homebrew/bin/brew ]; then
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    
    echo -e "${GREEN}Homebrew installed successfully${NC}"
}

# Function to install Docker Desktop
install_docker() {
    echo ""
    echo "=== Installing Docker Desktop ==="
    
    if command_exists docker; then
        echo -e "${GREEN}Docker is already installed${NC}"
        docker --version
        return 0
    fi
    
    echo "Installing Docker Desktop via Homebrew..."
    brew install --cask docker
    
    echo -e "${GREEN}Docker Desktop installed${NC}"
    echo -e "${YELLOW}Note: Please start Docker Desktop from Applications folder${NC}"
    echo "Waiting for Docker to start..."
    
    # Wait for Docker to start
    for i in {1..30}; do
        if docker info >/dev/null 2>&1; then
            echo -e "${GREEN}Docker is running${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
    done
    
    echo ""
    echo -e "${YELLOW}Docker Desktop installed but not running${NC}"
    echo "Please start Docker Desktop manually from Applications"
}

# Function to install Python
install_python() {
    echo ""
    echo "=== Installing Python ==="
    
    if command_exists python3; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        echo -e "${GREEN}Python is already installed: $PYTHON_VERSION${NC}"
        
        # Check if version is 3.11+
        MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
        MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
        
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
            return 0
        else
            echo -e "${YELLOW}Python version is too old, installing Python 3.11${NC}"
        fi
    fi
    
    echo "Installing Python 3.11 via Homebrew..."
    brew install python@3.11
    
    # Link Python 3.11
    brew link python@3.11
    
    echo -e "${GREEN}Python installed successfully${NC}"
    python3 --version
}

# Function to install PostgreSQL client
install_postgres_client() {
    echo ""
    echo "=== Installing PostgreSQL Client ==="
    
    if command_exists psql; then
        echo -e "${GREEN}PostgreSQL client is already installed${NC}"
        psql --version
        return 0
    fi
    
    echo "Installing PostgreSQL client via Homebrew..."
    brew install postgresql@16
    
    echo -e "${GREEN}PostgreSQL client installed${NC}"
}

# Function to install Redis client
install_redis_client() {
    echo ""
    echo "=== Installing Redis Client ==="
    
    if command_exists redis-cli; then
        echo -e "${GREEN}Redis client is already installed${NC}"
        redis-cli --version
        return 0
    fi
    
    echo "Installing Redis client via Homebrew..."
    brew install redis
    
    echo -e "${GREEN}Redis client installed${NC}"
}

# Function to install Python dependencies
install_python_deps() {
    echo ""
    echo "=== Installing Python Dependencies ==="
    
    # Install pip if not available
    if ! command_exists pip3; then
        echo "Installing pip..."
        python3 -m ensurepip --upgrade
    fi
    
    # Install virtualenv
    pip3 install --user virtualenv
    
    echo -e "${GREEN}Python dependencies installed${NC}"
}

# Function to display sandbox information
display_sandbox_info() {
    echo ""
    echo "=== Sandbox Information ==="
    echo ""
    echo -e "${YELLOW}Note: gVisor and Firecracker are not available on macOS${NC}"
    echo ""
    echo "The platform will use Docker Enhanced mode on macOS, which provides:"
    echo "  • Container-level isolation"
    echo "  • Resource limits (CPU, memory)"
    echo "  • Network isolation"
    echo "  • Capability dropping"
    echo ""
    echo "Security level: Medium"
    echo "Performance overhead: ~5%"
    echo ""
    echo "This is the recommended configuration for macOS development."
}

# Main installation flow
main() {
    echo ""
    echo "This script will install:"
    echo "  1. Homebrew (if not installed)"
    echo "  2. Docker Desktop"
    echo "  3. Python 3.11+"
    echo "  4. PostgreSQL client"
    echo "  5. Redis client"
    echo "  6. Python dependencies"
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled"
        exit 0
    fi
    
    # Install components
    install_homebrew
    install_docker
    install_python
    install_postgres_client
    install_redis_client
    install_python_deps
    display_sandbox_info
    
    echo ""
    echo "=== Setup Complete ==="
    echo ""
    echo -e "${GREEN}Installation completed successfully!${NC}"
    echo ""
    echo "Installed components:"
    command_exists brew && echo "  ✓ Homebrew: $(brew --version | head -n1)"
    command_exists docker && echo "  ✓ Docker: $(docker --version)"
    command_exists python3 && echo "  ✓ Python: $(python3 --version)"
    command_exists psql && echo "  ✓ PostgreSQL client: $(psql --version)"
    command_exists redis-cli && echo "  ✓ Redis client: $(redis-cli --version)"
    echo ""
    echo "Next steps:"
    echo "  1. Ensure Docker Desktop is running"
    echo "  2. Run: cd backend && python3 -m venv venv && source venv/bin/activate"
    echo "  3. Run: pip install -r requirements.txt"
    echo "  4. Run: docker-compose up -d"
    echo ""
    echo "For more information, see: docs/deployment/docker-compose-deployment.md"
}

# Run main function
main
