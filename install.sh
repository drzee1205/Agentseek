#!/bin/bash

set -e

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

error() {
    echo "❌ Error: $1" >&2
    exit 1
}

success() {
    echo "✅ $1"
}

check_prerequisites() {
    echo "🔍 Checking prerequisites..."
    
    if ! command_exists python3.10; then
        error "Python 3.10 is not installed"
    else
        echo "✅ Python 3.10 is installed"
    fi
    
    if ! command_exists pip3; then
        error "pip3 is not installed"
    else
        echo "✅ pip3 is installed"
    fi
    
    if ! command_exists docker; then
        error "Docker is not installed"
    else
        echo "✅ Docker is installed"
    fi
    
    if ! command_exists docker-compose; then
        error "Docker Compose is not installed"
    else
        echo "✅ Docker Compose is installed"
    fi
    
    if ! command_exists google-chrome; then
        error "Google Chrome is not installed"
    else
        echo "✅ Google Chrome is installed"
    fi
    
    success "All prerequisites are satisfied!"
}

install_pytorch() {
    echo "📦 Installing PyTorch..."
    python3.10 -m pip install torch==2.2.1 torchvision==0.17.1 torchaudio==2.2.1 --index-url https://download.pytorch.org/whl/cpu
    success "PyTorch installed successfully!"
}

# Install dependencies based on OS
install_dependencies() {
    echo "📦 Installing dependencies..."
    
    case "$(uname -s)" in
        Darwin*)
            echo "🍎 Detected macOS"
            
            if ! command_exists brew; then
                echo "❌ Homebrew not found. Installing Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            else
                echo "✅ Homebrew already installed"
            fi
            
            echo "📦 Updating Homebrew..."
            brew update
            
            echo "📦 Installing system dependencies..."
            brew install python@3.10 wget portaudio
            brew install --cask chromedriver
            
            echo "📦 Installing Python packages..."
            python3.10 -m pip install --upgrade pip setuptools wheel
            python3.10 -m pip install -r requirements-base.txt
            
            install_pytorch
            ;;
            
        Linux*)
            echo "🐧 Detected Linux"
            
            if command_exists apt-get; then
                echo "📦 Installing system dependencies (Debian/Ubuntu)..."
                sudo apt-get update
                sudo apt-get install -y python3.10 python3.10-dev python3.10-venv python3-pip wget portaudio19-dev
                sudo apt-get install -y chromium-chromedriver
            elif command_exists dnf; then
                echo "📦 Installing system dependencies (Fedora)..."
                sudo dnf install -y python3.10 python3.10-devel python3.10-pip wget portaudio-devel
                sudo dnf install -y chromium-chromedriver
            else
                error "Unsupported Linux distribution"
            fi
            
            echo "📦 Installing Python packages..."
            python3.10 -m pip install --upgrade pip setuptools wheel
            python3.10 -m pip install -r requirements-base.txt
            
            install_pytorch
            ;;
            
        *)
            error "Unsupported operating system"
            ;;
    esac
    
    success "Dependencies installed successfully!"
}

main() {
    echo "🚀 Starting installation process..."
    
    check_prerequisites
    install_dependencies
    
    if [ -d "venv" ]; then
        echo "⚠️ Virtual environment already exists. Skipping creation."
    else
        echo "📦 Creating virtual environment..."
        python3.10 -m venv venv
    fi
    
    echo "📦 Activating virtual environment..."
    source venv/bin/activate
    
    echo "📦 Installing Python packages..."
    pip install --upgrade pip setuptools wheel
    pip install -r requirements-base.txt
    
    install_pytorch
    
    success "Installation completed successfully!"
}

main
