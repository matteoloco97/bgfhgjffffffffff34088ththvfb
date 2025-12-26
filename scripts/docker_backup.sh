#!/bin/bash
# ============================================================================
# QuantumDev - Docker Backup Script
# Backup persistent data from Docker volumes
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS="${RETENTION_DAYS:-7}"

# Volume names (match docker-compose.yml)
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-quantumdev}"

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
    echo "  QuantumDev Docker Backup"
    echo "  Timestamp: ${TIMESTAMP}"
    echo "  Backup Dir: ${BACKUP_DIR}"
    echo "============================================"
    echo ""
}

backup_volume() {
    local volume_name=$1
    local backup_name=$2
    local full_volume_name="${COMPOSE_PROJECT_NAME}_${volume_name}"
    
    log_info "Backing up volume: ${full_volume_name}..."
    
    # Check if volume exists
    if ! docker volume ls --format '{{.Name}}' | grep -q "^${full_volume_name}$"; then
        log_warning "Volume ${full_volume_name} not found, skipping"
        return 0
    fi
    
    local backup_file="${BACKUP_DIR}/${backup_name}_${TIMESTAMP}.tar.gz"
    
    # Create backup using temporary container
    docker run --rm \
        -v "${full_volume_name}:/data:ro" \
        -v "$(realpath ${BACKUP_DIR}):/backup" \
        alpine:latest \
        tar czf "/backup/${backup_name}_${TIMESTAMP}.tar.gz" -C /data .
    
    if [ $? -eq 0 ]; then
        local size=$(du -h "${backup_file}" | cut -f1)
        log_success "Created ${backup_file} (${size})"
    else
        log_error "Failed to backup ${full_volume_name}"
        return 1
    fi
}

backup_redis() {
    log_info "Backing up Redis data..."
    
    # Trigger Redis BGSAVE before backup
    if docker exec quantumdev-redis redis-cli BGSAVE 2>/dev/null; then
        log_info "Redis BGSAVE triggered, waiting 5 seconds..."
        sleep 5
    fi
    
    backup_volume "redis-data" "redis"
}

backup_chromadb() {
    log_info "Backing up ChromaDB data..."
    backup_volume "chroma-data" "chromadb"
}

backup_prometheus() {
    log_info "Backing up Prometheus data..."
    backup_volume "prometheus-data" "prometheus"
}

backup_grafana() {
    log_info "Backing up Grafana data..."
    backup_volume "grafana-data" "grafana"
}

backup_logs() {
    log_info "Backing up application logs..."
    backup_volume "app-logs" "app-logs"
}

backup_all() {
    backup_redis
    backup_chromadb
    backup_prometheus
    backup_grafana
    backup_logs
}

restore_volume() {
    local backup_file=$1
    local volume_name=$2
    local full_volume_name="${COMPOSE_PROJECT_NAME}_${volume_name}"
    
    if [ ! -f "$backup_file" ]; then
        log_error "Backup file not found: $backup_file"
        return 1
    fi
    
    log_info "Restoring ${backup_file} to ${full_volume_name}..."
    
    # Warning
    log_warning "This will OVERWRITE existing data in ${full_volume_name}!"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Restore cancelled"
        return 0
    fi
    
    # Create volume if it doesn't exist
    docker volume create "${full_volume_name}" 2>/dev/null || true
    
    # Restore using temporary container
    docker run --rm \
        -v "${full_volume_name}:/data" \
        -v "$(realpath $(dirname ${backup_file})):/backup:ro" \
        alpine:latest \
        sh -c "rm -rf /data/* && tar xzf /backup/$(basename ${backup_file}) -C /data"
    
    if [ $? -eq 0 ]; then
        log_success "Restored ${full_volume_name} from ${backup_file}"
    else
        log_error "Failed to restore ${full_volume_name}"
        return 1
    fi
}

cleanup_old_backups() {
    log_info "Cleaning up backups older than ${RETENTION_DAYS} days..."
    
    local count=$(find "${BACKUP_DIR}" -name "*.tar.gz" -mtime +${RETENTION_DAYS} | wc -l)
    
    if [ "$count" -gt 0 ]; then
        find "${BACKUP_DIR}" -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete
        log_success "Removed ${count} old backup(s)"
    else
        log_info "No old backups to remove"
    fi
}

list_backups() {
    log_info "Available backups:"
    echo ""
    
    if [ -d "${BACKUP_DIR}" ]; then
        ls -lh "${BACKUP_DIR}"/*.tar.gz 2>/dev/null || echo "No backups found"
    else
        echo "Backup directory not found: ${BACKUP_DIR}"
    fi
}

show_usage() {
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  all           Backup all volumes (default)"
    echo "  redis         Backup Redis data"
    echo "  chromadb      Backup ChromaDB data"
    echo "  prometheus    Backup Prometheus data"
    echo "  grafana       Backup Grafana data"
    echo "  logs          Backup application logs"
    echo "  restore       Restore from backup"
    echo "  list          List available backups"
    echo "  cleanup       Remove old backups"
    echo ""
    echo "Options:"
    echo "  -d, --dir DIR       Backup directory (default: ./backups)"
    echo "  -r, --retention N   Retention days (default: 7)"
    echo "  -h, --help          Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                              # Backup all volumes"
    echo "  $0 redis -d /mnt/backup         # Backup Redis to custom dir"
    echo "  $0 restore backups/redis_*.tar.gz redis-data"
    echo "  $0 cleanup -r 30                # Keep 30 days of backups"
}

# Parse arguments
COMMAND=""
RESTORE_FILE=""
RESTORE_VOLUME=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--dir)
            BACKUP_DIR="$2"
            shift 2
            ;;
        -r|--retention)
            RETENTION_DAYS="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        all|redis|chromadb|prometheus|grafana|logs|list|cleanup)
            COMMAND="$1"
            shift
            ;;
        restore)
            COMMAND="restore"
            RESTORE_FILE="$2"
            RESTORE_VOLUME="$3"
            shift 3
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

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Default to all backups
COMMAND="${COMMAND:-all}"

# Execute command
print_header

case $COMMAND in
    all)
        backup_all
        cleanup_old_backups
        ;;
    redis)
        backup_redis
        ;;
    chromadb)
        backup_chromadb
        ;;
    prometheus)
        backup_prometheus
        ;;
    grafana)
        backup_grafana
        ;;
    logs)
        backup_logs
        ;;
    restore)
        if [ -z "$RESTORE_FILE" ] || [ -z "$RESTORE_VOLUME" ]; then
            log_error "Usage: $0 restore <backup_file> <volume_name>"
            exit 1
        fi
        restore_volume "$RESTORE_FILE" "$RESTORE_VOLUME"
        ;;
    list)
        list_backups
        ;;
    cleanup)
        cleanup_old_backups
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        show_usage
        exit 1
        ;;
esac

echo ""
log_success "Done!"
