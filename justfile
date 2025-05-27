# List of available commands
default:
    @just --list

# Install dependencies based on OS
install:
    #!/usr/bin/env bash
    echo "🔍 Detecting operating system..."
    case "$(uname -s)" in
        Darwin*)
            echo "🍎 Detected macOS"
            if ! command -v brew &> /dev/null; then
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
            
            echo "📦 Installing PyTorch..."
            python3.10 -m pip install torch==2.2.1 torchvision==0.17.1 torchaudio==2.2.1 --index-url https://download.pytorch.org/whl/cpu
            ;;
        Linux*)
            echo "🐧 Detected Linux"
            if command -v apt-get &> /dev/null; then
                echo "📦 Installing system dependencies (Debian/Ubuntu)..."
                sudo apt-get update
                sudo apt-get install -y python3.10 python3.10-dev python3.10-venv python3-pip wget portaudio19-dev
                sudo apt-get install -y chromium-chromedriver
                
                echo "📦 Installing Python packages..."
                python3.10 -m pip install --upgrade pip setuptools wheel
                python3.10 -m pip install -r requirements-base.txt
                
                echo "📦 Installing PyTorch..."
                python3.10 -m pip install torch==2.2.1 torchvision==0.17.1 torchaudio==2.2.1 --index-url https://download.pytorch.org/whl/cpu
            elif command -v dnf &> /dev/null; then
                echo "📦 Installing system dependencies (Fedora)..."
                sudo dnf install -y python3.10 python3.10-devel python3.10-pip wget portaudio-devel
                sudo dnf install -y chromium-chromedriver
                
                echo "📦 Installing Python packages..."
                python3.10 -m pip install --upgrade pip setuptools wheel
                python3.10 -m pip install -r requirements-base.txt
                
                echo "📦 Installing PyTorch..."
                python3.10 -m pip install torch==2.2.1 torchvision==0.17.1 torchaudio==2.2.1 --index-url https://download.pytorch.org/whl/cpu
            else
                echo "❌ Unsupported Linux distribution"
                exit 1
            fi
            ;;
        *)
            echo "❌ Unsupported operating system"
            exit 1
            ;;
    esac
    echo "✅ Installation completed successfully!"

# Check system requirements
check:
    #!/usr/bin/env bash
    echo "🔍 Checking system requirements..."
    case "$(uname -s)" in
        Darwin*)
            if ! command -v brew &> /dev/null; then
                echo "❌ Homebrew is not installed"
                echo "💡 Please install it first:"
                echo "/bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                exit 1
            else
                echo "✅ Homebrew is installed"
            fi
            ;;
    esac
    
    if ! command -v python3.10 &> /dev/null; then
        echo "❌ Python 3.10 is not installed"
        exit 1
    else
        echo "✅ Python 3.10 is installed"
    fi
    
    if ! command -v pip3 &> /dev/null; then
        echo "❌ pip3 is not installed"
        exit 1
    else
        echo "✅ pip3 is installed"
    fi
    
    echo "✅ All prerequisites are satisfied!"

# Setup virtual environment
setup-venv:
    #!/usr/bin/env bash
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
    
    echo "📦 Installing PyTorch..."
    pip install torch==2.2.1 torchvision==0.17.1 torchaudio==2.2.1 --index-url https://download.pytorch.org/whl/cpu
    
    echo "✅ Virtual environment setup completed!"

start:
    #!/usr/bin/env bash
    case "$(uname -s)" in
        Darwin*|Linux*)
            echo "🚀 Starting services..."
            ./start_services.sh
            ;;
        *)
            echo "❌ Unsupported operating system"
            exit 1
            ;;
    esac 