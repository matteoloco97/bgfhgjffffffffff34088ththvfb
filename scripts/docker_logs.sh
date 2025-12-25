#!/bin/bash
# ============================================================================
# QuantumDev - Docker Logs Script
# View and manage container logs
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
LINES="${LOG_LINES:-100}"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_usage() {
    echo "Usage: $0 [SERVICE] [OPTIONS]"
    echo ""
    echo "Services:"
    echo "  api           API server logs"
    echo "  bot           Telegram bot logs"
    echo "  redis         Redis logs"
    echo "  chromadb      ChromaDB logs"
    echo "  prometheus    Prometheus logs"
    echo "  grafana       Grafana logs"
    echo "  all           All services (default)"
    echo ""
    echo "Options:"
    echo "  -f, --follow      Follow log output"
    echo "  -n, --lines NUM   Number of lines to show (default: 100)"
    echo "  --since TIME      Show logs since timestamp (e.g., 10m, 1h, 2023-01-01)"
    echo "  --until TIME      Show logs until timestamp"
    echo "  --no-color        Disable colors"
    echo "  -h, --help        Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                      # Show last 100 lines of all services"
    echo "  $0 api -f               # Follow API logs"
    echo "  $0 bot -n 500           # Show last 500 lines of bot logs"
    echo "  $0 all --since 1h       # All logs from last hour"
}

get_container_name() {
    case $1 in
        api)
            echo "quantumdev-api"
            ;;
        bot|telegram-bot)
            echo "quantumdev-telegram-bot"
            ;;
        redis)
            echo "quantumdev-redis"
            ;;
        chromadb)
            echo "quantumdev-chromadb"
            ;;
        prometheus)
            echo "quantumdev-prometheus"
            ;;
        grafana)
            echo "quantumdev-grafana"
            ;;
        *)
            echo ""
            ;;
    esac
}

show_logs() {
    local service=$1
    local container_name=$(get_container_name "$service")
    
    if [ -z "$container_name" ]; then
        log_error "Unknown service: $service"
        return 1
    fi
    
    # Check if container exists
    if ! docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
        log_error "Container ${container_name} not found"
        return 1
    fi
    
    log_info "Logs for ${service} (${container_name}):"
    echo "============================================"
    
    local cmd="docker logs"
    
    [ -n "$FOLLOW" ] && cmd="$cmd -f"
    [ -n "$LINES" ] && cmd="$cmd --tail $LINES"
    [ -n "$SINCE" ] && cmd="$cmd --since $SINCE"
    [ -n "$UNTIL" ] && cmd="$cmd --until $UNTIL"
    [ -n "$NO_COLOR" ] || cmd="$cmd --timestamps"
    
    $cmd "$container_name"
}

show_all_logs() {
    log_info "Logs for all services:"
    echo "============================================"
    
    local cmd="docker-compose -p ${COMPOSE_PROJECT_NAME} logs"
    
    [ -n "$FOLLOW" ] && cmd="$cmd -f"
    [ -n "$LINES" ] && cmd="$cmd --tail $LINES"
    [ -n "$SINCE" ] && cmd="$cmd --since $SINCE"
    [ -n "$NO_COLOR" ] && cmd="$cmd --no-color"
    [ -n "$NO_COLOR" ] || cmd="$cmd --timestamps"
    
    $cmd
}

export_logs() {
    local output_dir="${1:-./logs_export}"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    
    mkdir -p "$output_dir"
    
    log_info "Exporting logs to ${output_dir}..."
    
    for service in api bot redis chromadb prometheus grafana; do
        local container_name=$(get_container_name "$service")
        if docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
            local output_file="${output_dir}/${service}_${timestamp}.log"
            docker logs "$container_name" > "$output_file" 2>&1
            log_info "Exported ${service} logs to ${output_file}"
        fi
    done
    
    # Create compressed archive
    local archive="${output_dir}/logs_${timestamp}.tar.gz"
    tar -czf "$archive" -C "$output_dir" .
    log_info "Created archive: ${archive}"
}

# Parse arguments
SERVICE=""
FOLLOW=""
SINCE=""
UNTIL=""
NO_COLOR=""
EXPORT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW="true"
            shift
            ;;
        -n|--lines)
            LINES="$2"
            shift 2
            ;;
        --since)
            SINCE="$2"
            shift 2
            ;;
        --until)
            UNTIL="$2"
            shift 2
            ;;
        --no-color)
            NO_COLOR="true"
            shift
            ;;
        --export)
            EXPORT="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        api|bot|telegram-bot|redis|chromadb|prometheus|grafana|all)
            SERVICE="$1"
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

# Handle export
if [ -n "$EXPORT" ]; then
    export_logs "$EXPORT"
    exit 0
fi

# Default to all services
SERVICE="${SERVICE:-all}"

# Show logs
if [ "$SERVICE" = "all" ]; then
    show_all_logs
else
    show_logs "$SERVICE"
fi
