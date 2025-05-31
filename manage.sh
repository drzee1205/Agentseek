#!/bin/bash

# AgenticSeek Management Script
# Easy management of AgenticSeek services

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

COMPOSE_FILE="docker-compose.prod.yml"

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

show_usage() {
    echo "AgenticSeek Management Script"
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  start       Start all services"
    echo "  stop        Stop all services"
    echo "  restart     Restart all services"
    echo "  status      Show service status"
    echo "  logs        Show logs (use -f for follow)"
    echo "  update      Update and rebuild services"
    echo "  backup      Create backup"
    echo "  monitor     Show system monitor"
    echo "  shell       Open shell in backend container"
    echo "  config      Edit configuration"
    echo "  cleanup     Clean up unused Docker resources"
    echo "  health      Check service health"
    echo ""
    echo "Examples:"
    echo "  $0 start"
    echo "  $0 logs -f backend"
    echo "  $0 shell"
}

check_compose_file() {
    if [ ! -f "$COMPOSE_FILE" ]; then
        print_error "Docker compose file not found: $COMPOSE_FILE"
        exit 1
    fi
}

start_services() {
    print_header "Starting AgenticSeek Services"
    check_compose_file
    
    docker-compose -f "$COMPOSE_FILE" up -d
    print_status "Services started"
    
    print_status "Waiting for services to be ready..."
    sleep 10
    
    docker-compose -f "$COMPOSE_FILE" ps
}

stop_services() {
    print_header "Stopping AgenticSeek Services"
    check_compose_file
    
    docker-compose -f "$COMPOSE_FILE" down
    print_status "Services stopped"
}

restart_services() {
    print_header "Restarting AgenticSeek Services"
    check_compose_file
    
    docker-compose -f "$COMPOSE_FILE" restart
    print_status "Services restarted"
    
    docker-compose -f "$COMPOSE_FILE" ps
}

show_status() {
    print_header "Service Status"
    check_compose_file
    
    docker-compose -f "$COMPOSE_FILE" ps
    echo ""
    
    print_header "Container Resource Usage"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
}

show_logs() {
    check_compose_file
    
    if [ "$2" = "-f" ]; then
        if [ -n "$3" ]; then
            print_header "Following logs for service: $3"
            docker-compose -f "$COMPOSE_FILE" logs -f "$3"
        else
            print_header "Following all logs"
            docker-compose -f "$COMPOSE_FILE" logs -f
        fi
    else
        if [ -n "$2" ]; then
            print_header "Logs for service: $2"
            docker-compose -f "$COMPOSE_FILE" logs --tail=50 "$2"
        else
            print_header "All service logs"
            docker-compose -f "$COMPOSE_FILE" logs --tail=50
        fi
    fi
}

update_services() {
    print_header "Updating AgenticSeek Services"
    check_compose_file
    
    print_status "Pulling latest images..."
    docker-compose -f "$COMPOSE_FILE" pull
    
    print_status "Rebuilding and restarting services..."
    docker-compose -f "$COMPOSE_FILE" up -d --build
    
    print_status "Update completed"
    docker-compose -f "$COMPOSE_FILE" ps
}

create_backup() {
    print_header "Creating Backup"
    
    if [ -f "./backup.sh" ]; then
        ./backup.sh
    else
        print_error "Backup script not found"
        exit 1
    fi
}

show_monitor() {
    print_header "System Monitor"
    
    if [ -f "./monitor.sh" ]; then
        ./monitor.sh
    else
        print_error "Monitor script not found"
        exit 1
    fi
}

open_shell() {
    print_header "Opening Shell in Backend Container"
    check_compose_file
    
    if docker-compose -f "$COMPOSE_FILE" ps | grep -q "agentic-backend.*Up"; then
        docker-compose -f "$COMPOSE_FILE" exec backend /bin/bash
    else
        print_error "Backend container is not running"
        exit 1
    fi
}

edit_config() {
    print_header "Configuration Files"
    echo "1) config.ini (Main configuration)"
    echo "2) .env (Environment variables)"
    echo "3) docker-compose.prod.yml (Docker configuration)"
    echo "4) nginx/nginx.conf (Nginx configuration)"
    echo ""
    read -p "Select file to edit (1-4): " choice
    
    case $choice in
        1)
            ${EDITOR:-nano} config.ini
            ;;
        2)
            ${EDITOR:-nano} .env
            ;;
        3)
            ${EDITOR:-nano} docker-compose.prod.yml
            ;;
        4)
            ${EDITOR:-nano} nginx/nginx.conf
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac
    
    read -p "Restart services to apply changes? (y/n): " restart_choice
    if [[ $restart_choice =~ ^[Yy]$ ]]; then
        restart_services
    fi
}

cleanup_docker() {
    print_header "Cleaning Up Docker Resources"
    
    print_status "Removing unused containers..."
    docker container prune -f
    
    print_status "Removing unused images..."
    docker image prune -f
    
    print_status "Removing unused volumes..."
    docker volume prune -f
    
    print_status "Removing unused networks..."
    docker network prune -f
    
    print_status "Docker cleanup completed"
    
    echo ""
    print_header "Disk Usage After Cleanup"
    df -h
}

check_health() {
    print_header "Health Check"
    
    # Check if services are running
    if docker-compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
        print_status "Containers are running"
    else
        print_error "Some containers are not running"
    fi
    
    # Check service endpoints
    if curl -f -s http://localhost/health > /dev/null 2>&1; then
        print_status "Web interface is accessible"
    else
        print_warning "Web interface is not accessible"
    fi
    
    if curl -f -s http://localhost/api/health > /dev/null 2>&1; then
        print_status "API is accessible"
    else
        print_warning "API is not accessible"
    fi
    
    # Check disk space
    local disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$disk_usage" -lt 90 ]; then
        print_status "Disk usage: ${disk_usage}%"
    else
        print_warning "Disk usage: ${disk_usage}% (High)"
    fi
    
    # Check memory
    local mem_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
    if [ "$mem_usage" -lt 90 ]; then
        print_status "Memory usage: ${mem_usage}%"
    else
        print_warning "Memory usage: ${mem_usage}% (High)"
    fi
}

# Main script logic
case "$1" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "$@"
        ;;
    update)
        update_services
        ;;
    backup)
        create_backup
        ;;
    monitor)
        show_monitor
        ;;
    shell)
        open_shell
        ;;
    config)
        edit_config
        ;;
    cleanup)
        cleanup_docker
        ;;
    health)
        check_health
        ;;
    *)
        show_usage
        exit 1
        ;;
esac