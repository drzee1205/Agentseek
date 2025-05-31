#!/bin/bash

# AgenticSeek Backup Script
# Creates backups of important data and configurations

set -e

# Configuration
BACKUP_DIR="/home/$(whoami)/agenticseek-backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="agenticseek_backup_$DATE"
RETENTION_DAYS=7

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create backup directory
mkdir -p "$BACKUP_DIR"

print_status "Starting AgenticSeek backup..."
print_status "Backup directory: $BACKUP_DIR"
print_status "Backup name: $BACKUP_NAME"

# Create temporary backup directory
TEMP_BACKUP_DIR="/tmp/$BACKUP_NAME"
mkdir -p "$TEMP_BACKUP_DIR"

# Function to backup file or directory
backup_item() {
    local source="$1"
    local dest_name="$2"
    
    if [ -e "$source" ]; then
        cp -r "$source" "$TEMP_BACKUP_DIR/$dest_name"
        print_status "Backed up: $source"
    else
        print_warning "Not found: $source"
    fi
}

# Backup configuration files
print_status "Backing up configuration files..."
backup_item "config.ini" "config.ini"
backup_item ".env" ".env"
backup_item ".env.production" ".env.production"
backup_item "docker-compose.prod.yml" "docker-compose.prod.yml"
backup_item "nginx/nginx.conf" "nginx.conf"

# Backup workspace
print_status "Backing up workspace..."
if [ -d "workspace" ]; then
    tar -czf "$TEMP_BACKUP_DIR/workspace.tar.gz" workspace/
    print_status "Workspace archived"
else
    print_warning "Workspace directory not found"
fi

# Backup screenshots
print_status "Backing up screenshots..."
if [ -d "screenshots" ]; then
    tar -czf "$TEMP_BACKUP_DIR/screenshots.tar.gz" screenshots/
    print_status "Screenshots archived"
else
    print_warning "Screenshots directory not found"
fi

# Backup Docker volumes (if accessible)
print_status "Backing up Docker volumes..."
if docker volume ls | grep -q "agenticseek"; then
    docker run --rm -v agenticseek_v1_redis-data:/data -v "$TEMP_BACKUP_DIR":/backup alpine tar -czf /backup/redis-data.tar.gz -C /data .
    print_status "Redis data backed up"
fi

# Create system info
print_status "Creating system information..."
cat > "$TEMP_BACKUP_DIR/system_info.txt" << EOF
AgenticSeek Backup Information
==============================
Backup Date: $(date)
Hostname: $(hostname)
OS: $(lsb_release -d | cut -f2)
Docker Version: $(docker --version)
Docker Compose Version: $(docker-compose --version)
Disk Usage: $(df -h /)
Memory: $(free -h)
Uptime: $(uptime)

Running Containers:
$(docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}")

Docker Volumes:
$(docker volume ls)

Docker Networks:
$(docker network ls)
EOF

# Create final backup archive
print_status "Creating final backup archive..."
cd /tmp
tar -czf "$BACKUP_DIR/$BACKUP_NAME.tar.gz" "$BACKUP_NAME/"

# Calculate backup size
BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_NAME.tar.gz" | cut -f1)
print_status "Backup created: $BACKUP_DIR/$BACKUP_NAME.tar.gz ($BACKUP_SIZE)"

# Cleanup temporary directory
rm -rf "$TEMP_BACKUP_DIR"

# Remove old backups
print_status "Cleaning up old backups (keeping last $RETENTION_DAYS days)..."
find "$BACKUP_DIR" -name "agenticseek_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete
REMAINING_BACKUPS=$(ls -1 "$BACKUP_DIR"/agenticseek_backup_*.tar.gz 2>/dev/null | wc -l)
print_status "Remaining backups: $REMAINING_BACKUPS"

# Create backup log
echo "$(date): Backup completed - $BACKUP_NAME.tar.gz ($BACKUP_SIZE)" >> "$BACKUP_DIR/backup.log"

print_status "Backup completed successfully!"
print_status "Backup location: $BACKUP_DIR/$BACKUP_NAME.tar.gz"
print_status "Backup size: $BACKUP_SIZE"

# Optional: Upload to cloud storage (uncomment and configure as needed)
# print_status "Uploading to cloud storage..."
# aws s3 cp "$BACKUP_DIR/$BACKUP_NAME.tar.gz" s3://your-backup-bucket/agenticseek/
# print_status "Cloud upload completed"