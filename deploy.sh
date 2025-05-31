#!/bin/bash

# AgenticSeek Digital Ocean Deployment Script
# This script helps deploy AgenticSeek to a Digital Ocean droplet

set -e

echo "🚀 AgenticSeek Digital Ocean Deployment Script"
echo "=============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root for security reasons"
   exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
print_header "Checking prerequisites..."

if ! command_exists docker; then
    print_error "Docker is not installed. Please install Docker first."
    echo "Run: curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh"
    exit 1
fi

if ! command_exists docker-compose; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    echo "Run: sudo curl -L \"https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-\$(uname -s)-\$(uname -m)\" -o /usr/local/bin/docker-compose"
    echo "Then: sudo chmod +x /usr/local/bin/docker-compose"
    exit 1
fi

print_status "Prerequisites check passed!"

# Create necessary directories
print_header "Creating necessary directories..."
mkdir -p workspace screenshots nginx/ssl

# Generate SearXNG secret key if not exists
if [ ! -f .env.production ]; then
    print_header "Setting up environment variables..."
    cp .env.production .env
    SEARXNG_SECRET=$(openssl rand -hex 32)
    sed -i "s/your-secret-key-here-change-this/$SEARXNG_SECRET/" .env
    print_status "Generated SearXNG secret key"
else
    print_status "Environment file already exists"
fi

# Setup configuration
print_header "Setting up configuration..."
if [ ! -f config.ini ]; then
    cp config.production.ini config.ini
    print_status "Created production configuration"
fi

# Function to setup API keys
setup_api_keys() {
    print_header "Setting up API keys..."
    echo "Please choose your LLM provider:"
    echo "1) OpenAI (GPT models)"
    echo "2) DeepSeek API"
    echo "3) Google Gemini"
    echo "4) Local Ollama (requires separate setup)"
    echo "5) Skip (configure manually later)"
    
    read -p "Enter your choice (1-5): " choice
    
    case $choice in
        1)
            read -p "Enter your OpenAI API key: " openai_key
            sed -i "s/OPENAI_API_KEY=/OPENAI_API_KEY=$openai_key/" .env
            sed -i "s/provider_name = openai/provider_name = openai/" config.ini
            sed -i "s/provider_model = gpt-4o-mini/provider_model = gpt-4o-mini/" config.ini
            sed -i "s/is_local = False/is_local = False/" config.ini
            print_status "OpenAI configuration set"
            ;;
        2)
            read -p "Enter your DeepSeek API key: " deepseek_key
            sed -i "s/DEEPSEEK_API_KEY=/DEEPSEEK_API_KEY=$deepseek_key/" .env
            sed -i "s/provider_name = openai/provider_name = deepseek/" config.ini
            sed -i "s/provider_model = gpt-4o-mini/provider_model = deepseek-chat/" config.ini
            sed -i "s/is_local = False/is_local = False/" config.ini
            print_status "DeepSeek configuration set"
            ;;
        3)
            read -p "Enter your Google API key: " google_key
            sed -i "s/GOOGLE_API_KEY=/GOOGLE_API_KEY=$google_key/" .env
            sed -i "s/provider_name = openai/provider_name = google/" config.ini
            sed -i "s/provider_model = gpt-4o-mini/provider_model = gemini-2.0-flash/" config.ini
            sed -i "s/is_local = False/is_local = False/" config.ini
            print_status "Google Gemini configuration set"
            ;;
        4)
            sed -i "s/provider_name = openai/provider_name = ollama/" config.ini
            sed -i "s/provider_model = gpt-4o-mini/provider_model = deepseek-r1:14b/" config.ini
            sed -i "s/is_local = False/is_local = True/" config.ini
            print_warning "Local Ollama selected. Make sure Ollama is running on the host machine."
            print_warning "Install Ollama: curl -fsSL https://ollama.ai/install.sh | sh"
            print_warning "Pull model: ollama pull deepseek-r1:14b"
            ;;
        5)
            print_warning "Skipping API key setup. Please configure manually in .env and config.ini files."
            ;;
        *)
            print_error "Invalid choice. Skipping API key setup."
            ;;
    esac
}

# Ask user if they want to setup API keys
read -p "Do you want to setup API keys now? (y/n): " setup_keys
if [[ $setup_keys =~ ^[Yy]$ ]]; then
    setup_api_keys
fi

# Build and start services
print_header "Building and starting services..."
print_status "This may take several minutes on first run..."

# Stop any existing containers
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# Build and start services
if docker-compose -f docker-compose.prod.yml up --build -d; then
    print_status "Services started successfully!"
else
    print_error "Failed to start services. Check the logs with: docker-compose -f docker-compose.prod.yml logs"
    exit 1
fi

# Wait for services to be ready
print_header "Waiting for services to be ready..."
sleep 30

# Check service health
print_header "Checking service health..."

# Check if containers are running
if docker-compose -f docker-compose.prod.yml ps | grep -q "Up"; then
    print_status "Containers are running"
else
    print_error "Some containers are not running. Check logs with: docker-compose -f docker-compose.prod.yml logs"
fi

# Check if nginx is responding
if curl -f http://localhost/health >/dev/null 2>&1; then
    print_status "Nginx is responding"
else
    print_warning "Nginx health check failed. The service might still be starting up."
fi

# Display final information
print_header "Deployment completed!"
echo ""
echo "🎉 AgenticSeek has been deployed successfully!"
echo ""
echo "📋 Service Information:"
echo "   • Web Interface: http://your-server-ip/"
echo "   • API Endpoint: http://your-server-ip/api/"
echo "   • Health Check: http://your-server-ip/health"
echo ""
echo "🔧 Management Commands:"
echo "   • View logs: docker-compose -f docker-compose.prod.yml logs -f"
echo "   • Stop services: docker-compose -f docker-compose.prod.yml down"
echo "   • Restart services: docker-compose -f docker-compose.prod.yml restart"
echo "   • Update services: docker-compose -f docker-compose.prod.yml pull && docker-compose -f docker-compose.prod.yml up -d"
echo ""
echo "📁 Important Files:"
echo "   • Configuration: config.ini"
echo "   • Environment: .env"
echo "   • Workspace: ./workspace/"
echo "   • Screenshots: ./screenshots/"
echo ""
echo "🔒 Security Notes:"
echo "   • Change default passwords and API keys"
echo "   • Configure SSL certificates for production use"
echo "   • Set up firewall rules"
echo "   • Regular backups of workspace and configuration"
echo ""

# Show running containers
print_header "Running containers:"
docker-compose -f docker-compose.prod.yml ps

print_status "Deployment script completed!"