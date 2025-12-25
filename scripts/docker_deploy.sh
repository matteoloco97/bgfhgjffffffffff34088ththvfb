#!/bin/bash
# ============================================================================
# QuantumDev - Docker Deploy Script
# Deploys the application using Docker Compose
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-quantumdev}"
ENV_FILE="${ENV_FILE:-.env}"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo "============================================"
    echo "  QuantumDev Docker Deploy"
    echo "  Environment: ${ENVIRONMENT:-development}"
    echo "  Project: ${COMPOSE_PROJECT_NAME}"
    echo "============================================"
    echo ""
}

check_requirements() {
    log_info "Checking requirements..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check .env file
    if [ ! -f "${ENV_FILE}" ]; then
        log_warning ".env file not found at ${ENV_FILE}"
        if [ -f ".env.example" ]; then
            log_info "Copying .env.example to .env"
            cp .env.example .env
        else
            log_error "No .env.example found. Please create .env file"
            exit 1
        fi
    fi
    
    log_success "Requirements check passed"
}

deploy_dev() {
    log_info "Deploying development environment..."
    
    docker-compose \
        -p "${COMPOSE_PROJECT_NAME}" \
        -f docker-compose.yml \
        -f docker-compose.dev.yml \
        --env-file "${ENV_FILE}" \
        up -d --build
    
    log_success "Development environment deployed"
}

deploy_prod() {
    log_info "Deploying production environment..."
    
    # Build images first
    log_info "Building images..."
    docker-compose \
        -p "${COMPOSE_PROJECT_NAME}" \
        -f docker-compose.yml \
        -f docker-compose.prod.yml \
        --env-file "${ENV_FILE}" \
        build
    
    # Deploy with rolling update
    log_info "Starting services..."
    docker-compose \
        -p "${COMPOSE_PROJECT_NAME}" \
        -f docker-compose.yml \
        -f docker-compose.prod.yml \
        --env-file "${ENV_FILE}" \
        up -d
    
    log_success "Production environment deployed"
}

stop_services() {
    log_info "Stopping all services..."
    
    docker-compose \
        -p "${COMPOSE_PROJECT_NAME}" \
        down
    
    log_success "All services stopped"
}

restart_services() {
    log_info "Restarting services..."
    
    if [ "${ENVIRONMENT}" = "production" ]; then
        docker-compose \
            -p "${COMPOSE_PROJECT_NAME}" \
            -f docker-compose.yml \
            -f docker-compose.prod.yml \
            --env-file "${ENV_FILE}" \
            restart
    else
        docker-compose \
            -p "${COMPOSE_PROJECT_NAME}" \
            -f docker-compose.yml \
            -f docker-compose.dev.yml \
            --env-file "${ENV_FILE}" \
            restart
    fi
    
    log_success "Services restarted"
}

status() {
    log_info "Service status:"
    echo ""
    
    docker-compose \
        -p "${COMPOSE_PROJECT_NAME}" \
        ps
    
    echo ""
    log_info "Health check:"
    
    # Check API health
    if curl -sf http://localhost:8081/healthz > /dev/null 2>&1; then
        log_success "API: Healthy"
    else
        log_error "API: Unhealthy or not running"
    fi
    
    # Check Redis
    if docker exec quantumdev-redis redis-cli ping > /dev/null 2>&1; then
        log_success "Redis: Healthy"
    else
        log_error "Redis: Unhealthy or not running"
    fi
    
    # Check ChromaDB
    if curl -sf http://localhost:8000/api/v1/heartbeat > /dev/null 2>&1; then
        log_success "ChromaDB: Healthy"
    else
        log_error "ChromaDB: Unhealthy or not running"
    fi
    
    # Check Prometheus
    if curl -sf http://localhost:9090/-/healthy > /dev/null 2>&1; then
        log_success "Prometheus: Healthy"
    else
        log_warning "Prometheus: Unhealthy or not running"
    fi
    
    # Check Grafana
    if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
        log_success "Grafana: Healthy"
    else
        log_warning "Grafana: Unhealthy or not running"
    fi
}

cleanup() {
    log_info "Cleaning up unused Docker resources..."
    
    # Remove stopped containers
    docker container prune -f
    
    # Remove unused images
    docker image prune -f
    
    # Remove unused volumes (be careful!)
    read -p "Remove unused volumes? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker volume prune -f
    fi
    
    log_success "Cleanup completed"
}

show_usage() {
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  dev         Deploy development environment"
    echo "  prod        Deploy production environment"
    echo "  stop        Stop all services"
    echo "  restart     Restart all services"
    echo "  status      Show service status"
    echo "  cleanup     Clean up unused Docker resources"
    echo "  help        Show this help"
    echo ""
    echo "Options:"
    echo "  -e, --env FILE    Environment file (default: .env)"
    echo "  -p, --project     Compose project name"
    echo ""
    echo "Examples:"
    echo "  $0 dev                    # Deploy development"
    echo "  $0 prod -e .env.prod      # Deploy production with custom env"
    echo "  $0 status                 # Check service status"
}

# Parse arguments
COMMAND=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--env)
            ENV_FILE="$2"
            shift 2
            ;;
        -p|--project)
            COMPOSE_PROJECT_NAME="$2"
            shift 2
            ;;
        dev|prod|stop|restart|status|cleanup|help)
            COMMAND="$1"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Change to project root
cd "$(dirname "$0")/.."

# Execute command
print_header

case $COMMAND in
    dev)
        check_requirements
        ENVIRONMENT="development"
        deploy_dev
        ;;
    prod)
        check_requirements
        ENVIRONMENT="production"
        deploy_prod
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        status
        ;;
    cleanup)
        cleanup
        ;;
    help|"")
        show_usage
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        show_usage
        exit 1
        ;;
esac

echo ""
log_info "Done!"
