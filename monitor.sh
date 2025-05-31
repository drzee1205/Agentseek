#!/bin/bash

# AgenticSeek Monitoring Script
# Monitors system health and service status

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Function to check service health
check_service_health() {
    local service_name=$1
    local url=$2
    
    if curl -f -s "$url" > /dev/null 2>&1; then
        print_status "$service_name is healthy"
        return 0
    else
        print_error "$service_name is not responding"
        return 1
    fi
}

# Function to check container status
check_container_status() {
    local container_name=$1
    
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "$container_name.*Up"; then
        print_status "$container_name is running"
        return 0
    else
        print_error "$container_name is not running"
        return 1
    fi
}

# Function to get container stats
get_container_stats() {
    echo "Container Resource Usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}"
}

# Function to check disk space
check_disk_space() {
    local usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [ "$usage" -lt 80 ]; then
        print_status "Disk usage: ${usage}% (OK)"
    elif [ "$usage" -lt 90 ]; then
        print_warning "Disk usage: ${usage}% (Warning)"
    else
        print_error "Disk usage: ${usage}% (Critical)"
    fi
}

# Function to check memory usage
check_memory_usage() {
    local mem_info=$(free | grep Mem)
    local total=$(echo $mem_info | awk '{print $2}')
    local used=$(echo $mem_info | awk '{print $3}')
    local usage=$((used * 100 / total))
    
    if [ "$usage" -lt 80 ]; then
        print_status "Memory usage: ${usage}% (OK)"
    elif [ "$usage" -lt 90 ]; then
        print_warning "Memory usage: ${usage}% (Warning)"
    else
        print_error "Memory usage: ${usage}% (Critical)"
    fi
}

# Function to check load average
check_load_average() {
    local load=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
    local cores=$(nproc)
    local load_percent=$(echo "$load * 100 / $cores" | bc -l | cut -d. -f1)
    
    if [ "$load_percent" -lt 70 ]; then
        print_status "Load average: $load (${load_percent}% of $cores cores)"
    elif [ "$load_percent" -lt 90 ]; then
        print_warning "Load average: $load (${load_percent}% of $cores cores)"
    else
        print_error "Load average: $load (${load_percent}% of $cores cores)"
    fi
}

# Main monitoring function
main() {
    clear
    echo -e "${BLUE}"
    echo "  ___                  _   _      ___           _    "
    echo " / _ \                | | (_)    / __\         | |   "
    echo "/ /_\ \ __ _  ___ _ __ | |_ _  __/ /  ___  ___  | | __"
    echo "|  _  |/ _\` |/ _ \ '_ \| __| |/ / /  / _ \/ _ \ | |/ /"
    echo "| | | | (_| |  __/ | | | |_| / / /__|  __/  __/ |   < "
    echo "\_| |_/\__, |\___|_| |_|\__|_\____/\___|\___|_|_|\_\\"
    echo "        __/ |                                        "
    echo "       |___/                                         "
    echo -e "${NC}"
    echo "AgenticSeek System Monitor"
    echo "=========================="
    echo "Timestamp: $(date)"
    echo ""

    # System Health
    print_header "System Health"
    check_disk_space
    check_memory_usage
    check_load_average
    echo ""

    # Container Status
    print_header "Container Status"
    check_container_status "agentic-nginx"
    check_container_status "agentic-frontend"
    check_container_status "agentic-backend"
    check_container_status "agentic-searxng"
    check_container_status "agentic-redis"
    echo ""

    # Service Health
    print_header "Service Health"
    check_service_health "Nginx" "http://localhost/health"
    check_service_health "Backend API" "http://localhost/api/health"
    check_service_health "SearXNG" "http://localhost:8080"
    echo ""

    # Resource Usage
    print_header "Resource Usage"
    get_container_stats
    echo ""

    # Docker Compose Status
    print_header "Docker Compose Status"
    if [ -f "docker-compose.prod.yml" ]; then
        docker-compose -f docker-compose.prod.yml ps
    else
        print_error "docker-compose.prod.yml not found"
    fi
    echo ""

    # Recent Logs (last 10 lines)
    print_header "Recent Logs"
    echo "Backend logs (last 5 lines):"
    docker-compose -f docker-compose.prod.yml logs --tail=5 backend 2>/dev/null || echo "No backend logs available"
    echo ""
    echo "Nginx logs (last 5 lines):"
    docker-compose -f docker-compose.prod.yml logs --tail=5 nginx 2>/dev/null || echo "No nginx logs available"
    echo ""

    # Network Status
    print_header "Network Status"
    echo "Docker networks:"
    docker network ls | grep agentic
    echo ""

    # Volume Status
    print_header "Volume Status"
    echo "Docker volumes:"
    docker volume ls | grep agentic
    echo ""

    print_header "Monitoring Complete"
    echo "For continuous monitoring, run: watch -n 30 ./monitor.sh"
    echo "For detailed logs, run: docker-compose -f docker-compose.prod.yml logs -f"
}

# Check if running in watch mode
if [ "$1" = "--watch" ]; then
    watch -n 30 "$0"
else
    main
fi