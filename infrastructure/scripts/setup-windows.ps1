# Platform-specific setup script for Windows
# This script installs and configures required components for Windows

# Requires PowerShell 5.1 or later and Administrator privileges

#Requires -RunAsAdministrator

Write-Host "=== Digital Workforce Platform - Windows Setup ===" -ForegroundColor Cyan
Write-Host ""

# Check Windows version
$osInfo = Get-CimInstance -ClassName Win32_OperatingSystem
$windowsVersion = $osInfo.Version
Write-Host "Detected: Windows $windowsVersion" -ForegroundColor Green

# Function to check if command exists
function Test-CommandExists {
    param($command)
    $null = Get-Command $command -ErrorAction SilentlyContinue
    return $?
}

# Function to install Chocolatey
function Install-Chocolatey {
    Write-Host ""
    Write-Host "=== Installing Chocolatey ===" -ForegroundColor Cyan
    
    if (Test-CommandExists choco) {
        Write-Host "Chocolatey is already installed" -ForegroundColor Green
        choco --version
        return
    }
    
    Write-Host "Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    
    # Refresh environment variables
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    
    Write-Host "Chocolatey installed successfully" -ForegroundColor Green
}

# Function to install Docker Desktop
function Install-Docker {
    Write-Host ""
    Write-Host "=== Installing Docker Desktop ===" -ForegroundColor Cyan
    
    if (Test-CommandExists docker) {
        Write-Host "Docker is already installed" -ForegroundColor Green
        docker --version
        return
    }
    
    Write-Host "Installing Docker Desktop via Chocolatey..."
    choco install docker-desktop -y
    
    Write-Host "Docker Desktop installed" -ForegroundColor Green
    Write-Host "Note: Please restart your computer and start Docker Desktop" -ForegroundColor Yellow
    Write-Host "Docker Desktop requires WSL 2. If not installed, Docker will prompt you." -ForegroundColor Yellow
}

# Function to install WSL 2
function Install-WSL2 {
    Write-Host ""
    Write-Host "=== Checking WSL 2 ===" -ForegroundColor Cyan
    
    $wslVersion = wsl --status 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "WSL is already installed" -ForegroundColor Green
        wsl --version
        return
    }
    
    Write-Host "Installing WSL 2..."
    Write-Host "This requires a system restart" -ForegroundColor Yellow
    
    # Enable WSL feature
    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
    
    # Enable Virtual Machine Platform
    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
    
    # Download and install WSL 2 kernel update
    $wslUpdateUrl = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
    $wslUpdatePath = "$env:TEMP\wsl_update_x64.msi"
    
    Write-Host "Downloading WSL 2 kernel update..."
    Invoke-WebRequest -Uri $wslUpdateUrl -OutFile $wslUpdatePath
    
    Write-Host "Installing WSL 2 kernel update..."
    Start-Process msiexec.exe -ArgumentList "/i $wslUpdatePath /quiet" -Wait
    
    # Set WSL 2 as default
    wsl --set-default-version 2
    
    Write-Host "WSL 2 installed successfully" -ForegroundColor Green
    Write-Host "Please restart your computer for changes to take effect" -ForegroundColor Yellow
}

# Function to install Python
function Install-Python {
    Write-Host ""
    Write-Host "=== Installing Python ===" -ForegroundColor Cyan
    
    if (Test-CommandExists python) {
        $pythonVersion = python --version
        Write-Host "Python is already installed: $pythonVersion" -ForegroundColor Green
        
        # Check if version is 3.11+
        $version = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        $major, $minor = $version.Split('.')
        
        if ([int]$major -ge 3 -and [int]$minor -ge 11) {
            return
        } else {
            Write-Host "Python version is too old, installing Python 3.11" -ForegroundColor Yellow
        }
    }
    
    Write-Host "Installing Python 3.11 via Chocolatey..."
    choco install python311 -y
    
    # Refresh environment variables
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    
    Write-Host "Python installed successfully" -ForegroundColor Green
    python --version
}

# Function to install Git
function Install-Git {
    Write-Host ""
    Write-Host "=== Installing Git ===" -ForegroundColor Cyan
    
    if (Test-CommandExists git) {
        Write-Host "Git is already installed" -ForegroundColor Green
        git --version
        return
    }
    
    Write-Host "Installing Git via Chocolatey..."
    choco install git -y
    
    # Refresh environment variables
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    
    Write-Host "Git installed successfully" -ForegroundColor Green
}

# Function to install Python dependencies
function Install-PythonDeps {
    Write-Host ""
    Write-Host "=== Installing Python Dependencies ===" -ForegroundColor Cyan
    
    # Upgrade pip
    python -m pip install --upgrade pip
    
    # Install virtualenv
    pip install virtualenv
    
    Write-Host "Python dependencies installed" -ForegroundColor Green
}

# Function to display sandbox information
function Show-SandboxInfo {
    Write-Host ""
    Write-Host "=== Sandbox Information ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Note: gVisor and Firecracker are not available on Windows" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The platform will use Docker Enhanced mode on Windows, which provides:"
    Write-Host "  • Container-level isolation"
    Write-Host "  • Resource limits (CPU, memory)"
    Write-Host "  • Network isolation"
    Write-Host "  • Capability dropping"
    Write-Host ""
    Write-Host "Security level: Medium"
    Write-Host "Performance overhead: ~5%"
    Write-Host ""
    Write-Host "This is the recommended configuration for Windows development."
}

# Function to check Hyper-V
function Test-HyperV {
    Write-Host ""
    Write-Host "=== Checking Hyper-V ===" -ForegroundColor Cyan
    
    $hyperv = Get-WindowsOptionalFeature -FeatureName Microsoft-Hyper-V-All -Online
    
    if ($hyperv.State -eq "Enabled") {
        Write-Host "Hyper-V is enabled" -ForegroundColor Green
        return $true
    } else {
        Write-Host "Hyper-V is not enabled" -ForegroundColor Yellow
        Write-Host "Docker Desktop requires Hyper-V or WSL 2" -ForegroundColor Yellow
        return $false
    }
}

# Main installation flow
function Main {
    Write-Host ""
    Write-Host "This script will install:"
    Write-Host "  1. Chocolatey (package manager)"
    Write-Host "  2. WSL 2 (Windows Subsystem for Linux)"
    Write-Host "  3. Docker Desktop"
    Write-Host "  4. Python 3.11+"
    Write-Host "  5. Git"
    Write-Host "  6. Python dependencies"
    Write-Host ""
    
    $response = Read-Host "Continue? (y/n)"
    if ($response -ne 'y' -and $response -ne 'Y') {
        Write-Host "Installation cancelled"
        exit 0
    }
    
    # Check if running as administrator
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    $isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    
    if (-not $isAdmin) {
        Write-Host "Error: This script must be run as Administrator" -ForegroundColor Red
        Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
        exit 1
    }
    
    # Install components
    Install-Chocolatey
    Test-HyperV
    Install-WSL2
    Install-Docker
    Install-Python
    Install-Git
    Install-PythonDeps
    Show-SandboxInfo
    
    Write-Host ""
    Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Installation completed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Installed components:"
    if (Test-CommandExists choco) { Write-Host "  ✓ Chocolatey: $(choco --version)" }
    if (Test-CommandExists docker) { Write-Host "  ✓ Docker: $(docker --version)" }
    if (Test-CommandExists python) { Write-Host "  ✓ Python: $(python --version)" }
    if (Test-CommandExists git) { Write-Host "  ✓ Git: $(git --version)" }
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Restart your computer (required for WSL 2 and Docker)"
    Write-Host "  2. Start Docker Desktop from Start Menu"
    Write-Host "  3. Open PowerShell and run: cd backend"
    Write-Host "  4. Run: python -m venv venv"
    Write-Host "  5. Run: .\venv\Scripts\Activate.ps1"
    Write-Host "  6. Run: pip install -r requirements.txt"
    Write-Host "  7. Run: docker-compose up -d"
    Write-Host ""
    Write-Host "For more information, see: docs\deployment\docker-compose-deployment.md"
    Write-Host ""
    
    $restart = Read-Host "Restart computer now? (y/n)"
    if ($restart -eq 'y' -or $restart -eq 'Y') {
        Write-Host "Restarting computer in 10 seconds..." -ForegroundColor Yellow
        Start-Sleep -Seconds 10
        Restart-Computer -Force
    }
}

# Run main function
Main
