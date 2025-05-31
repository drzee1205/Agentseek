# AgenticSeek Digital Ocean Deployment Guide

Hướng dẫn deploy AgenticSeek lên Digital Ocean để sử dụng online.

## 📋 Yêu cầu hệ thống

### Digital Ocean Droplet
- **RAM**: Tối thiểu 4GB (khuyến nghị 8GB+)
- **CPU**: 2 vCPUs trở lên
- **Storage**: 50GB SSD
- **OS**: Ubuntu 22.04 LTS

### Phần mềm cần thiết
- Docker & Docker Compose
- Git
- Curl/Wget

## 🚀 Hướng dẫn deployment

### Bước 1: Tạo Digital Ocean Droplet

1. Đăng nhập vào Digital Ocean
2. Tạo droplet mới:
   - **Image**: Ubuntu 22.04 LTS
   - **Size**: Basic plan, 4GB RAM, 2 vCPUs ($24/month)
   - **Region**: Chọn region gần nhất
   - **Authentication**: SSH keys (khuyến nghị) hoặc password

### Bước 2: Kết nối và cài đặt

```bash
# Kết nối SSH vào droplet
ssh root@your-droplet-ip

# Cập nhật hệ thống
apt update && apt upgrade -y

# Cài đặt Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Cài đặt Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Cài đặt Git
apt install git -y
```

### Bước 3: Clone và deploy

```bash
# Clone repository
git clone https://github.com/zeroxf89/agenticSeek_v1.git
cd agenticSeek_v1

# Chạy script deployment
./deploy.sh
```

Script sẽ tự động:
- Kiểm tra prerequisites
- Tạo các thư mục cần thiết
- Thiết lập environment variables
- Cấu hình API keys
- Build và start các services

### Bước 4: Cấu hình LLM Provider

Chọn một trong các options sau:

#### Option 1: OpenAI API (Khuyến nghị cho bắt đầu)
```bash
# Trong quá trình chạy deploy.sh, chọn option 1 và nhập OpenAI API key
# Hoặc edit thủ công:
nano .env
# Thêm: OPENAI_API_KEY=your-api-key-here

nano config.ini
# Cấu hình:
# provider_name = openai
# provider_model = gpt-4o-mini
# is_local = False
```

#### Option 2: Local Ollama (Tiết kiệm chi phí)
```bash
# Cài đặt Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull model
ollama pull deepseek-r1:14b

# Cấu hình trong config.ini:
# provider_name = ollama
# provider_model = deepseek-r1:14b
# is_local = True
```

#### Option 3: DeepSeek API (Giá rẻ)
```bash
# Đăng ký tại https://platform.deepseek.com/
# Cấu hình:
# provider_name = deepseek
# provider_model = deepseek-chat
# DEEPSEEK_API_KEY=your-api-key
```

### Bước 5: Cấu hình Firewall

```bash
# Cài đặt UFW
ufw enable

# Mở các ports cần thiết
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp

# Kiểm tra status
ufw status
```

### Bước 6: Cấu hình Domain (Tùy chọn)

```bash
# Nếu có domain, cấu hình DNS A record trỏ về IP droplet
# Sau đó cấu hình SSL:

# Cài đặt Certbot
apt install certbot python3-certbot-nginx -y

# Tạo SSL certificate
certbot --nginx -d your-domain.com

# Uncomment HTTPS server block trong nginx/nginx.conf
```

## 🔧 Quản lý Services

### Xem logs
```bash
docker-compose -f docker-compose.prod.yml logs -f
```

### Restart services
```bash
docker-compose -f docker-compose.prod.yml restart
```

### Stop services
```bash
docker-compose -f docker-compose.prod.yml down
```

### Update services
```bash
git pull
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d --build
```

## 🌐 Truy cập ứng dụng

- **Web Interface**: `http://your-droplet-ip/`
- **API**: `http://your-droplet-ip/api/`
- **Health Check**: `http://your-droplet-ip/health`

## 🔒 Bảo mật

### 1. Thay đổi passwords mặc định
```bash
# Tạo user non-root
adduser agenticseek
usermod -aG sudo agenticseek
usermod -aG docker agenticseek

# Disable root login
nano /etc/ssh/sshd_config
# PermitRootLogin no
systemctl restart ssh
```

### 2. Cấu hình SSL
```bash
# Sử dụng Let's Encrypt (miễn phí)
certbot --nginx -d your-domain.com
```

### 3. Backup định kỳ
```bash
# Tạo script backup
cat > /home/agenticseek/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
tar -czf /home/agenticseek/backup_$DATE.tar.gz \
    /home/agenticseek/agenticSeek_v1/workspace \
    /home/agenticseek/agenticSeek_v1/config.ini \
    /home/agenticseek/agenticSeek_v1/.env
EOF

chmod +x /home/agenticseek/backup.sh

# Cron job backup hàng ngày
crontab -e
# Thêm: 0 2 * * * /home/agenticseek/backup.sh
```

## 🐛 Troubleshooting

### Service không start
```bash
# Kiểm tra logs
docker-compose -f docker-compose.prod.yml logs

# Kiểm tra disk space
df -h

# Kiểm tra memory
free -h
```

### Chrome driver issues
```bash
# Restart backend container
docker-compose -f docker-compose.prod.yml restart backend
```

### API không response
```bash
# Kiểm tra backend logs
docker-compose -f docker-compose.prod.yml logs backend

# Kiểm tra network
docker network ls
```

## 💰 Chi phí ước tính

### Digital Ocean Droplet
- **4GB RAM**: $24/month
- **8GB RAM**: $48/month

### LLM API costs
- **OpenAI GPT-4o-mini**: ~$0.15/1M tokens
- **DeepSeek**: ~$0.14/1M tokens  
- **Local Ollama**: Miễn phí (cần RAM nhiều hơn)

## 📞 Hỗ trợ

Nếu gặp vấn đề:
1. Kiểm tra logs: `docker-compose -f docker-compose.prod.yml logs`
2. Kiểm tra GitHub Issues
3. Discord community: https://discord.gg/8hGDaME3TC

## 🔄 Updates

Để update lên version mới:
```bash
cd agenticSeek_v1
git pull
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --build
```