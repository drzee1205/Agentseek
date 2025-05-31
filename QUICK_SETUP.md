# 🚀 AgenticSeek - Setup Siêu Nhanh

## 📋 Bước 1: Tạo Digital Ocean Droplet

1. Đăng nhập [Digital Ocean](https://digitalocean.com)
2. Tạo Droplet mới:
   - **Image**: Ubuntu 22.04 LTS
   - **Size**: Basic - 4GB RAM, 2 vCPUs ($24/month)
   - **Region**: Singapore hoặc gần nhất
   - **Authentication**: SSH Key (khuyến nghị) hoặc Password

## 🔑 Bước 2: SSH vào Server

```bash
ssh root@YOUR_DROPLET_IP
```

## ⚡ Bước 3: Chạy Lệnh Duy Nhất

```bash
curl -fsSL https://raw.githubusercontent.com/zeroxf89/agenticSeek_v1/main/auto-deploy.sh | bash
```

**HOẶC** nếu muốn tải về trước:

```bash
wget https://raw.githubusercontent.com/zeroxf89/agenticSeek_v1/main/auto-deploy.sh
chmod +x auto-deploy.sh
./auto-deploy.sh
```

## 🎯 Bước 4: Nhập Thông Tin Khi Được Hỏi

Script sẽ hỏi:

### 1. Chọn LLM Provider:
- **Option 1**: OpenAI (khuyến nghị) - cần API key
- **Option 2**: DeepSeek (rẻ) - cần API key  
- **Option 3**: Google Gemini - cần API key
- **Option 4**: Local Ollama (miễn phí, cần RAM nhiều)

### 2. Nhập API Key (nếu chọn option 1-3)
- Lấy từ trang web của provider

### 3. Tên AI Assistant
- Mặc định: AgenticSeek

### 4. Lưu session hay không
- Mặc định: Yes

## ✅ Bước 5: Đợi Hoàn Tất

Script sẽ tự động:
- ✅ Cài đặt Docker & Docker Compose
- ✅ Cấu hình firewall
- ✅ Tải mã nguồn
- ✅ Thiết lập cấu hình
- ✅ Deploy tất cả services
- ✅ Thiết lập monitoring & backup

**Thời gian**: 10-15 phút

## 🌐 Bước 6: Truy Cập & Sử Dụng

Sau khi hoàn tất, truy cập:
- **Web Interface**: `http://YOUR_DROPLET_IP/`
- **API**: `http://YOUR_DROPLET_IP/api/`

## 🔧 Quản Lý Đơn Giản

```bash
cd agenticSeek_v1

# Xem trạng thái
./manage.sh status

# Xem logs
./manage.sh logs -f

# Restart nếu có vấn đề
./manage.sh restart

# Backup dữ liệu
./manage.sh backup

# Monitor hệ thống
./manage.sh monitor
```

## 💰 Chi Phí Ước Tính

- **Digital Ocean**: $24/month (4GB RAM)
- **OpenAI API**: ~$0.15/1M tokens (~$5-10/month sử dụng bình thường)
- **DeepSeek API**: ~$0.14/1M tokens (~$3-8/month)
- **Local Ollama**: Miễn phí (cần 8GB RAM = $48/month droplet)

## 🆘 Nếu Có Vấn Đề

```bash
# Kiểm tra logs
./manage.sh logs backend

# Kiểm tra health
./manage.sh health

# Restart tất cả
./manage.sh restart

# Xem hướng dẫn chi tiết
cat DEPLOYMENT.md
```

## 📞 Hỗ Trợ

- **GitHub**: [Issues](https://github.com/zeroxf89/agenticSeek_v1/issues)
- **Discord**: [Community](https://discord.gg/8hGDaME3TC)

---

**🎉 Chỉ cần 6 bước đơn giản và bạn có AgenticSeek chạy online!**