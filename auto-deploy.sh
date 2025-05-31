#!/bin/bash

# AgenticSeek One-Click Auto Deployment Script
# Chỉ cần chạy script này trên Digital Ocean droplet và nhập thông tin khi được hỏi

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

print_banner() {
    clear
    echo -e "${PURPLE}"
    echo "  ___                  _   _      ___           _    "
    echo " / _ \                | | (_)    / __\         | |   "
    echo "/ /_\ \ __ _  ___ _ __ | |_ _  __/ /  ___  ___  | | __"
    echo "|  _  |/ _\` |/ _ \ '_ \| __| |/ / /  / _ \/ _ \ | |/ /"
    echo "| | | | (_| |  __/ | | | |_| / / /__|  __/  __/ |   < "
    echo "\_| |_/\__, |\___|_| |_|\__|_\____/\___|\___|_|_|\_\\"
    echo "        __/ |                                        "
    echo "       |___/                                         "
    echo -e "${NC}"
    echo -e "${BLUE}🚀 AgenticSeek One-Click Auto Deployment${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_status() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_info() {
    echo -e "${PURPLE}[INFO]${NC} $1"
}

# Function to check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "Vui lòng không chạy script này với quyền root"
        print_info "Tạo user thường và chạy lại script"
        exit 1
    fi
}

# Function to install prerequisites
install_prerequisites() {
    print_step "Cài đặt các phần mềm cần thiết..."
    
    # Update system
    sudo apt update -y
    sudo apt upgrade -y
    
    # Install basic tools
    sudo apt install -y curl wget git unzip software-properties-common apt-transport-https ca-certificates gnupg lsb-release
    
    # Install Docker
    if ! command -v docker &> /dev/null; then
        print_info "Cài đặt Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh get-docker.sh
        sudo usermod -aG docker $USER
        rm get-docker.sh
        print_status "Docker đã được cài đặt"
    else
        print_status "Docker đã có sẵn"
    fi
    
    # Install Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_info "Cài đặt Docker Compose..."
        sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
        print_status "Docker Compose đã được cài đặt"
    else
        print_status "Docker Compose đã có sẵn"
    fi
    
    # Install other tools
    sudo apt install -y htop nano vim ufw fail2ban
    
    print_status "Tất cả phần mềm cần thiết đã được cài đặt"
}

# Function to setup firewall
setup_firewall() {
    print_step "Cấu hình firewall..."
    
    sudo ufw --force enable
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow ssh
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    
    print_status "Firewall đã được cấu hình"
}

# Function to clone repository
clone_repository() {
    print_step "Tải mã nguồn AgenticSeek..."
    
    if [ -d "agenticSeek_v1" ]; then
        print_info "Thư mục đã tồn tại, đang cập nhật..."
        cd agenticSeek_v1
        git pull
        cd ..
    else
        git clone https://github.com/zeroxf89/agenticSeek_v1.git
    fi
    
    cd agenticSeek_v1
    print_status "Mã nguồn đã được tải"
}

# Function to collect user input
collect_user_input() {
    print_step "Thu thập thông tin cấu hình..."
    
    echo ""
    echo -e "${YELLOW}Vui lòng nhập thông tin cấu hình:${NC}"
    echo ""
    
    # LLM Provider selection
    echo "Chọn nhà cung cấp LLM:"
    echo "1) OpenAI (GPT-4o-mini) - Khuyến nghị"
    echo "2) DeepSeek API - Giá rẻ"
    echo "3) Google Gemini - Miễn phí có hạn"
    echo "4) Local Ollama - Miễn phí nhưng cần RAM nhiều"
    echo ""
    read -p "Nhập lựa chọn (1-4): " llm_choice
    
    case $llm_choice in
        1)
            LLM_PROVIDER="openai"
            LLM_MODEL="gpt-4o-mini"
            IS_LOCAL="False"
            echo ""
            read -p "Nhập OpenAI API Key: " OPENAI_API_KEY
            ;;
        2)
            LLM_PROVIDER="deepseek"
            LLM_MODEL="deepseek-chat"
            IS_LOCAL="False"
            echo ""
            read -p "Nhập DeepSeek API Key: " DEEPSEEK_API_KEY
            ;;
        3)
            LLM_PROVIDER="google"
            LLM_MODEL="gemini-2.0-flash"
            IS_LOCAL="False"
            echo ""
            read -p "Nhập Google API Key: " GOOGLE_API_KEY
            ;;
        4)
            LLM_PROVIDER="ollama"
            LLM_MODEL="deepseek-r1:14b"
            IS_LOCAL="True"
            print_warning "Bạn sẽ cần cài đặt Ollama sau khi deployment hoàn tất"
            ;;
        *)
            print_error "Lựa chọn không hợp lệ"
            exit 1
            ;;
    esac
    
    echo ""
    read -p "Tên cho AI assistant (mặc định: AgenticSeek): " AGENT_NAME
    AGENT_NAME=${AGENT_NAME:-AgenticSeek}
    
    echo ""
    read -p "Có muốn bật tính năng lưu session không? (y/n, mặc định: y): " SAVE_SESSION
    SAVE_SESSION=${SAVE_SESSION:-y}
    if [[ $SAVE_SESSION =~ ^[Yy]$ ]]; then
        SAVE_SESSION_BOOL="True"
        RECOVER_SESSION_BOOL="True"
    else
        SAVE_SESSION_BOOL="False"
        RECOVER_SESSION_BOOL="False"
    fi
    
    print_status "Thông tin cấu hình đã được thu thập"
}

# Function to setup configuration
setup_configuration() {
    print_step "Thiết lập cấu hình..."
    
    # Generate secrets
    SEARXNG_SECRET=$(openssl rand -hex 32)
    
    # Create .env file
    cat > .env << EOF
# Production Environment Variables for AgenticSeek
SEARXNG_SECRET_KEY=$SEARXNG_SECRET
OLLAMA_URL=http://host.docker.internal:11434
LM_STUDIO_URL=http://host.docker.internal:1234
OPENAI_API_KEY=${OPENAI_API_KEY:-}
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}
GOOGLE_API_KEY=${GOOGLE_API_KEY:-}
HUGGINGFACE_API_KEY=
TOGETHER_API_KEY=
REDIS_URL=redis://redis:6379/0
NODE_ENV=production
PYTHONUNBUFFERED=1
CORS_ORIGINS=http://localhost,https://$(curl -s ifconfig.me)
LOG_LEVEL=INFO
EOF
    
    # Create config.ini
    cat > config.ini << EOF
[MAIN]
is_local = $IS_LOCAL
provider_name = $LLM_PROVIDER
provider_model = $LLM_MODEL
provider_server_address = 127.0.0.1:11434
agent_name = $AGENT_NAME
recover_last_session = $RECOVER_SESSION_BOOL
save_session = $SAVE_SESSION_BOOL
speak = False
listen = False
work_dir = /app/workspace
jarvis_personality = False
languages = en vi

[BROWSER]
headless_browser = True
stealth_mode = True
EOF
    
    # Create necessary directories
    mkdir -p workspace screenshots nginx/ssl
    
    print_status "Cấu hình đã được thiết lập"
}

# Function to install Ollama if needed
install_ollama() {
    if [ "$LLM_PROVIDER" = "ollama" ]; then
        print_step "Cài đặt Ollama..."
        
        curl -fsSL https://ollama.ai/install.sh | sh
        
        print_info "Đang tải model $LLM_MODEL (có thể mất vài phút)..."
        ollama serve &
        sleep 10
        ollama pull $LLM_MODEL
        
        print_status "Ollama và model đã được cài đặt"
    fi
}

# Function to deploy services
deploy_services() {
    print_step "Triển khai các dịch vụ..."
    
    # Start Docker service
    sudo systemctl start docker
    sudo systemctl enable docker
    
    # Build and start services
    docker-compose -f docker-compose.prod.yml down 2>/dev/null || true
    docker-compose -f docker-compose.prod.yml up --build -d
    
    print_status "Các dịch vụ đã được triển khai"
}

# Function to wait for services
wait_for_services() {
    print_step "Đợi các dịch vụ khởi động..."
    
    echo "Đang đợi các dịch vụ sẵn sàng (có thể mất 1-2 phút)..."
    sleep 60
    
    # Check service health
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f -s http://localhost/health > /dev/null 2>&1; then
            print_status "Tất cả dịch vụ đã sẵn sàng"
            return 0
        fi
        
        echo "Đang đợi... (lần thử $attempt/$max_attempts)"
        sleep 10
        ((attempt++))
    done
    
    print_warning "Một số dịch vụ có thể chưa sẵn sàng, nhưng deployment đã hoàn tất"
}

# Function to setup monitoring
setup_monitoring() {
    print_step "Thiết lập monitoring..."
    
    # Create systemd service for monitoring
    sudo tee /etc/systemd/system/agenticseek-monitor.service > /dev/null << EOF
[Unit]
Description=AgenticSeek Monitor
After=docker.service

[Service]
Type=oneshot
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/monitor.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    # Create systemd timer for monitoring
    sudo tee /etc/systemd/system/agenticseek-monitor.timer > /dev/null << EOF
[Unit]
Description=Run AgenticSeek Monitor every 5 minutes
Requires=agenticseek-monitor.service

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable agenticseek-monitor.timer
    sudo systemctl start agenticseek-monitor.timer
    
    print_status "Monitoring đã được thiết lập"
}

# Function to setup backup
setup_backup() {
    print_step "Thiết lập backup tự động..."
    
    # Add backup to crontab
    (crontab -l 2>/dev/null; echo "0 2 * * * $(pwd)/backup.sh") | crontab -
    
    print_status "Backup tự động đã được thiết lập (chạy hàng ngày lúc 2:00 AM)"
}

# Function to display final information
display_final_info() {
    local server_ip=$(curl -s ifconfig.me)
    
    print_banner
    echo -e "${GREEN}🎉 DEPLOYMENT HOÀN TẤT THÀNH CÔNG! 🎉${NC}"
    echo ""
    echo -e "${BLUE}📋 THÔNG TIN TRUY CẬP:${NC}"
    echo -e "   🌐 Web Interface: ${GREEN}http://$server_ip/${NC}"
    echo -e "   🔗 API Endpoint:  ${GREEN}http://$server_ip/api/${NC}"
    echo -e "   ❤️  Health Check:  ${GREEN}http://$server_ip/health${NC}"
    echo ""
    echo -e "${BLUE}🔧 LỆNH QUẢN LÝ:${NC}"
    echo -e "   📊 Xem trạng thái:     ${YELLOW}./manage.sh status${NC}"
    echo -e "   📝 Xem logs:           ${YELLOW}./manage.sh logs -f${NC}"
    echo -e "   🔄 Restart dịch vụ:    ${YELLOW}./manage.sh restart${NC}"
    echo -e "   💾 Tạo backup:         ${YELLOW}./manage.sh backup${NC}"
    echo -e "   📈 Monitor hệ thống:   ${YELLOW}./manage.sh monitor${NC}"
    echo -e "   🔄 Cập nhật:           ${YELLOW}./manage.sh update${NC}"
    echo ""
    echo -e "${BLUE}⚙️  CẤU HÌNH:${NC}"
    echo -e "   🤖 LLM Provider: ${GREEN}$LLM_PROVIDER${NC}"
    echo -e "   🧠 Model: ${GREEN}$LLM_MODEL${NC}"
    echo -e "   👤 Agent Name: ${GREEN}$AGENT_NAME${NC}"
    echo -e "   💾 Save Session: ${GREEN}$SAVE_SESSION_BOOL${NC}"
    echo ""
    echo -e "${BLUE}📁 FILES QUAN TRỌNG:${NC}"
    echo -e "   ⚙️  Cấu hình chính: ${YELLOW}config.ini${NC}"
    echo -e "   🔐 Environment: ${YELLOW}.env${NC}"
    echo -e "   📂 Workspace: ${YELLOW}./workspace/${NC}"
    echo -e "   📸 Screenshots: ${YELLOW}./screenshots/${NC}"
    echo ""
    echo -e "${BLUE}🔒 BẢO MẬT:${NC}"
    echo -e "   🛡️  Firewall: ${GREEN}Đã cấu hình${NC}"
    echo -e "   🔥 Fail2ban: ${GREEN}Đã cài đặt${NC}"
    echo -e "   📊 Monitoring: ${GREEN}Đã thiết lập${NC}"
    echo -e "   💾 Auto Backup: ${GREEN}Hàng ngày 2:00 AM${NC}"
    echo ""
    
    if [ "$LLM_PROVIDER" = "ollama" ]; then
        echo -e "${YELLOW}⚠️  LƯU Ý OLLAMA:${NC}"
        echo -e "   Ollama đang chạy local, đảm bảo model đã được tải:"
        echo -e "   ${YELLOW}ollama list${NC}"
        echo ""
    fi
    
    echo -e "${BLUE}📞 HỖ TRỢ:${NC}"
    echo -e "   📚 Tài liệu: ${YELLOW}DEPLOYMENT.md${NC}"
    echo -e "   🐛 Báo lỗi: ${YELLOW}https://github.com/zeroxf89/agenticSeek_v1/issues${NC}"
    echo -e "   💬 Discord: ${YELLOW}https://discord.gg/8hGDaME3TC${NC}"
    echo ""
    echo -e "${GREEN}✨ Bạn có thể bắt đầu sử dụng AgenticSeek ngay bây giờ!${NC}"
    echo -e "${GREEN}   Truy cập: http://$server_ip/${NC}"
    echo ""
}

# Main execution
main() {
    print_banner
    
    echo -e "${YELLOW}Script này sẽ tự động cài đặt và cấu hình AgenticSeek trên server này.${NC}"
    echo -e "${YELLOW}Quá trình có thể mất 10-15 phút.${NC}"
    echo ""
    read -p "Bạn có muốn tiếp tục? (y/n): " confirm
    
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo "Deployment đã bị hủy."
        exit 0
    fi
    
    check_root
    install_prerequisites
    setup_firewall
    clone_repository
    collect_user_input
    setup_configuration
    install_ollama
    deploy_services
    wait_for_services
    setup_monitoring
    setup_backup
    display_final_info
}

# Run main function
main "$@"