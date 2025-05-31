# 🚀 AgenticSeek Digital Ocean Deployment

Deploy AgenticSeek lên Digital Ocean để sử dụng online một cách dễ dàng.

## ⚡ Quick Start

### 1. Tạo Digital Ocean Droplet
- **Size**: 4GB RAM, 2 vCPUs ($24/month)
- **OS**: Ubuntu 22.04 LTS
- **Region**: Chọn gần nhất

### 2. SSH vào server và chạy lệnh sau:

```bash
# Cài đặt Docker
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh

# Cài đặt Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Clone và deploy
git clone https://github.com/zeroxf89/agenticSeek_v1.git
cd agenticSeek_v1
./deploy.sh
```

### 3. Truy cập ứng dụng
- **Web Interface**: `http://your-server-ip/`
- **API**: `http://your-server-ip/api/`

## 🛠️ Quản lý dễ dàng

```bash
# Xem trạng thái
./manage.sh status

# Xem logs
./manage.sh logs -f

# Restart services
./manage.sh restart

# Backup dữ liệu
./manage.sh backup

# Monitor hệ thống
./manage.sh monitor

# Cập nhật
./manage.sh update
```

## 🔧 Cấu hình LLM

### Option 1: OpenAI (Khuyến nghị)
```bash
# Edit .env file
nano .env
# Thêm: OPENAI_API_KEY=your-api-key

# Edit config.ini
nano config.ini
# provider_name = openai
# provider_model = gpt-4o-mini
```

### Option 2: Local Ollama (Tiết kiệm)
```bash
# Cài Ollama
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull deepseek-r1:14b

# Cấu hình
# provider_name = ollama
# provider_model = deepseek-r1:14b
# is_local = True
```

## 📁 Files quan trọng

- `deploy.sh` - Script deployment tự động
- `manage.sh` - Quản lý services
- `monitor.sh` - Monitor hệ thống
- `backup.sh` - Backup tự động
- `docker-compose.prod.yml` - Production config
- `DEPLOYMENT.md` - Hướng dẫn chi tiết

## 💰 Chi phí

- **Digital Ocean Droplet**: $24/month (4GB RAM)
- **OpenAI API**: ~$0.15/1M tokens
- **DeepSeek API**: ~$0.14/1M tokens
- **Local Ollama**: Miễn phí (cần RAM nhiều hơn)

## 🔒 Bảo mật

```bash
# Cấu hình firewall
ufw enable
ufw allow ssh
ufw allow 80
ufw allow 443

# SSL certificate (nếu có domain)
apt install certbot python3-certbot-nginx -y
certbot --nginx -d your-domain.com
```

## 🆘 Troubleshooting

```bash
# Kiểm tra logs
./manage.sh logs backend

# Kiểm tra health
./manage.sh health

# Restart nếu có vấn đề
./manage.sh restart

# Cleanup Docker
./manage.sh cleanup
```

## 📞 Hỗ trợ

- **GitHub Issues**: [Report bugs](https://github.com/zeroxf89/agenticSeek_v1/issues)
- **Discord**: [Join community](https://discord.gg/8hGDaME3TC)
- **Documentation**: `DEPLOYMENT.md` (chi tiết đầy đủ)

---

**Lưu ý**: Đây là bản deployment production-ready với monitoring, backup, và security cơ bản. Đọc `DEPLOYMENT.md` để biết thêm chi tiết.