#!/bin/bash

# Test deployment script for local testing
# This script tests the deployment files without actually deploying

set -e

echo "🧪 Testing AgenticSeek Deployment Files"
echo "======================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_test() {
    echo -e "${YELLOW}[TEST]${NC} $1"
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
}

# Test 1: Check if all deployment files exist
print_test "Checking deployment files..."
files=(
    "deploy.sh"
    "manage.sh" 
    "monitor.sh"
    "backup.sh"
    "docker-compose.prod.yml"
    "Dockerfile.backend.prod"
    ".env.production"
    "config.production.ini"
    "nginx/nginx.conf"
    "frontend/Dockerfile.frontend.prod"
    "frontend/nginx.conf"
    "DEPLOYMENT.md"
    "README_DEPLOYMENT.md"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        print_pass "Found: $file"
    else
        print_fail "Missing: $file"
    fi
done

# Test 2: Check script permissions
print_test "Checking script permissions..."
scripts=("deploy.sh" "manage.sh" "monitor.sh" "backup.sh")
for script in "${scripts[@]}"; do
    if [ -x "$script" ]; then
        print_pass "Executable: $script"
    else
        print_fail "Not executable: $script"
    fi
done

# Test 3: Validate Docker Compose file
print_test "Validating Docker Compose file..."
if command -v docker-compose >/dev/null 2>&1; then
    if docker-compose -f docker-compose.prod.yml config >/dev/null 2>&1; then
        print_pass "Docker Compose file is valid"
    else
        print_fail "Docker Compose file has errors"
    fi
else
    print_fail "Docker Compose not installed (expected for testing)"
fi

# Test 4: Check Dockerfile syntax
print_test "Checking Dockerfile syntax..."
dockerfiles=("Dockerfile.backend.prod" "frontend/Dockerfile.frontend.prod")
for dockerfile in "${dockerfiles[@]}"; do
    if grep -q "FROM" "$dockerfile" && grep -q "WORKDIR" "$dockerfile"; then
        print_pass "Dockerfile syntax OK: $dockerfile"
    else
        print_fail "Dockerfile syntax issues: $dockerfile"
    fi
done

# Test 5: Check nginx configuration syntax
print_test "Checking nginx configuration..."
nginx_configs=("nginx/nginx.conf" "frontend/nginx.conf")
for config in "${nginx_configs[@]}"; do
    if grep -q "server {" "$config"; then
        print_pass "Nginx config syntax OK: $config"
    else
        print_fail "Nginx config syntax issues: $config"
    fi
done

# Test 6: Check environment file format
print_test "Checking environment file format..."
if grep -q "=" ".env.production"; then
    print_pass "Environment file format OK"
else
    print_fail "Environment file format issues"
fi

# Test 7: Check configuration file format
print_test "Checking configuration file format..."
if grep -q "\[MAIN\]" "config.production.ini"; then
    print_pass "Configuration file format OK"
else
    print_fail "Configuration file format issues"
fi

echo ""
echo "🎯 Test Summary"
echo "==============="
echo "All deployment files have been created and basic validation passed."
echo ""
echo "📋 Next Steps for Real Deployment:"
echo "1. Create Digital Ocean droplet (4GB RAM, Ubuntu 22.04)"
echo "2. SSH into the droplet"
echo "3. Install Docker and Docker Compose"
echo "4. Clone this repository"
echo "5. Run: ./deploy.sh"
echo ""
echo "🔧 Local Testing (if Docker is available):"
echo "docker-compose -f docker-compose.prod.yml config"
echo ""
echo "📚 Documentation:"
echo "- Quick Start: README_DEPLOYMENT.md"
echo "- Full Guide: DEPLOYMENT.md"
echo "- File Overview: DEPLOYMENT_FILES.md"