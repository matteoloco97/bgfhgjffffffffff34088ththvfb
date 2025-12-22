#!/bin/bash
# ============================================================
# QUANTUMDEV BACKUP AUTOMATION SCRIPT
# ============================================================
# Backs up critical QuantumDev components:
# - ChromaDB vector database
# - Redis database
# - Configuration files (.env)
# - Conversation archives
# - Service configurations
#
# Usage: 
#   ./backup.sh                    # Full backup
#   ./backup.sh --quick            # Skip ChromaDB (faster)
#   ./backup.sh --restore <DATE>   # Restore from backup
#
# Schedule with cron:
#   0 3 * * * /root/quantumdev-open/scripts/backup.sh >> /root/quantumdev-open/logs/backup.log 2>&1
#
# Deploy to: /root/quantumdev-open/scripts/backup.sh
# Make executable: chmod +x /root/quantumdev-open/scripts/backup.sh

set -e  # Exit on error

# ============================================================
# CONFIGURATION
# ============================================================
PROJECT_ROOT="/root/quantumdev-open"
BACKUP_BASE_DIR="/root/quantumdev-backups"
DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$BACKUP_BASE_DIR/$DATE"
RETENTION_DAYS=7
QUICK_MODE=0
RESTORE_MODE=0
RESTORE_DATE=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================
# FUNCTIONS
# ============================================================

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

check_dependencies() {
    log_info "Checking dependencies..."
    
    if ! command -v redis-cli &> /dev/null; then
        log_error "redis-cli not found. Install with: apt install redis-tools"
        exit 1
    fi
    
    if ! command -v tar &> /dev/null; then
        log_error "tar not found"
        exit 1
    fi
    
    log_success "All dependencies satisfied"
}

backup_chromadb() {
    log_info "Backing up ChromaDB..."
    
    CHROMA_DIR="/memory/chroma"
    if [ ! -d "$CHROMA_DIR" ]; then
        log_warning "ChromaDB directory not found: $CHROMA_DIR"
        return 1
    fi
    
    # Calculate size before backup
    SIZE=$(du -sh "$CHROMA_DIR" | cut -f1)
    log_info "ChromaDB size: $SIZE"
    
    # Create compressed backup
    tar -czf "$BACKUP_DIR/chroma.tar.gz" -C /memory chroma/ 2>/dev/null || {
        log_error "ChromaDB backup failed"
        return 1
    }
    
    BACKUP_SIZE=$(du -sh "$BACKUP_DIR/chroma.tar.gz" | cut -f1)
    log_success "ChromaDB backed up: $BACKUP_SIZE"
    return 0
}

backup_redis() {
    log_info "Backing up Redis..."
    
    # Trigger Redis BGSAVE
    redis-cli BGSAVE >/dev/null 2>&1 || {
        log_warning "Redis BGSAVE failed, trying SAVE..."
        redis-cli SAVE >/dev/null 2>&1 || {
            log_error "Redis backup failed"
            return 1
        }
    }
    
    # Wait for BGSAVE to complete
    sleep 2
    
    # Copy RDB file
    if [ -f /var/lib/redis/dump.rdb ]; then
        cp /var/lib/redis/dump.rdb "$BACKUP_DIR/redis-dump.rdb" || {
            log_error "Failed to copy Redis dump"
            return 1
        }
        SIZE=$(du -sh "$BACKUP_DIR/redis-dump.rdb" | cut -f1)
        log_success "Redis backed up: $SIZE"
    else
        log_warning "Redis dump.rdb not found"
        return 1
    fi
    
    return 0
}

backup_config() {
    log_info "Backing up configuration files..."
    
    mkdir -p "$BACKUP_DIR/config"
    
    # Backup .env
    if [ -f "$PROJECT_ROOT/.env" ]; then
        cp "$PROJECT_ROOT/.env" "$BACKUP_DIR/config/.env"
        log_success ".env backed up"
    else
        log_warning ".env not found"
    fi
    
    # Backup source_policy.yaml
    if [ -f "$PROJECT_ROOT/config/source_policy.yaml" ]; then
        cp "$PROJECT_ROOT/config/source_policy.yaml" "$BACKUP_DIR/config/"
        log_success "source_policy.yaml backed up"
    fi
    
    # Backup systemd services
    if [ -d "$PROJECT_ROOT/Service" ]; then
        cp -r "$PROJECT_ROOT/Service" "$BACKUP_DIR/config/"
        log_success "Systemd services backed up"
    fi
    
    return 0
}

backup_archives() {
    log_info "Backing up conversation archives..."
    
    ARCHIVE_DIR="$PROJECT_ROOT/data/archive"
    if [ -d "$ARCHIVE_DIR" ]; then
        tar -czf "$BACKUP_DIR/archives.tar.gz" -C "$PROJECT_ROOT/data" archive/ 2>/dev/null || {
            log_warning "Archive backup failed"
            return 1
        }
        SIZE=$(du -sh "$BACKUP_DIR/archives.tar.gz" | cut -f1)
        log_success "Archives backed up: $SIZE"
    else
        log_info "No archives directory found"
    fi
    
    return 0
}

backup_logs() {
    log_info "Backing up recent logs..."
    
    LOG_DIR="$PROJECT_ROOT/logs"
    if [ -d "$LOG_DIR" ]; then
        # Only backup logs from last 7 days
        find "$LOG_DIR" -name "*.log" -mtime -7 -exec tar -czf "$BACKUP_DIR/logs.tar.gz" {} +
        if [ -f "$BACKUP_DIR/logs.tar.gz" ]; then
            SIZE=$(du -sh "$BACKUP_DIR/logs.tar.gz" | cut -f1)
            log_success "Logs backed up: $SIZE"
        fi
    fi
    
    return 0
}

create_manifest() {
    log_info "Creating backup manifest..."
    
    cat > "$BACKUP_DIR/MANIFEST.txt" <<EOF
QuantumDev Backup Manifest
==========================
Date: $DATE
Hostname: $(hostname)
User: $(whoami)

Contents:
---------
EOF
    
    # List all backup files with sizes
    ls -lh "$BACKUP_DIR" | tail -n +2 >> "$BACKUP_DIR/MANIFEST.txt"
    
    # Add system info
    cat >> "$BACKUP_DIR/MANIFEST.txt" <<EOF

System Information:
-------------------
Disk Usage: $(df -h / | tail -1 | awk '{print $5 " used"}')
Memory: $(free -h | grep Mem | awk '{print $3 "/" $2}')
Uptime: $(uptime -p)

Services Status:
----------------
EOF
    
    systemctl is-active quantum-api >> "$BACKUP_DIR/MANIFEST.txt" 2>&1 || echo "quantum-api: not running" >> "$BACKUP_DIR/MANIFEST.txt"
    systemctl is-active telegram-bot >> "$BACKUP_DIR/MANIFEST.txt" 2>&1 || echo "telegram-bot: not running" >> "$BACKUP_DIR/MANIFEST.txt"
    redis-cli ping >> "$BACKUP_DIR/MANIFEST.txt" 2>&1 || echo "redis: not running" >> "$BACKUP_DIR/MANIFEST.txt"
    
    log_success "Manifest created"
}

cleanup_old_backups() {
    log_info "Cleaning up old backups (older than $RETENTION_DAYS days)..."
    
    DELETED=0
    while IFS= read -r -d '' backup; do
        rm -rf "$backup"
        DELETED=$((DELETED + 1))
    done < <(find "$BACKUP_BASE_DIR" -maxdepth 1 -type d -mtime +$RETENTION_DAYS -print0)
    
    if [ $DELETED -gt 0 ]; then
        log_success "Deleted $DELETED old backup(s)"
    else
        log_info "No old backups to delete"
    fi
}

verify_backup() {
    log_info "Verifying backup integrity..."
    
    ERRORS=0
    
    # Verify ChromaDB backup
    if [ -f "$BACKUP_DIR/chroma.tar.gz" ]; then
        tar -tzf "$BACKUP_DIR/chroma.tar.gz" >/dev/null 2>&1 || {
            log_error "ChromaDB backup corrupted"
            ERRORS=$((ERRORS + 1))
        }
    fi
    
    # Verify Redis backup
    if [ -f "$BACKUP_DIR/redis-dump.rdb" ]; then
        redis-cli --rdb "$BACKUP_DIR/redis-dump.rdb" check >/dev/null 2>&1 || {
            log_warning "Redis backup verification skipped (redis-check-rdb not available)"
        }
    fi
    
    # Verify archives
    if [ -f "$BACKUP_DIR/archives.tar.gz" ]; then
        tar -tzf "$BACKUP_DIR/archives.tar.gz" >/dev/null 2>&1 || {
            log_error "Archives backup corrupted"
            ERRORS=$((ERRORS + 1))
        }
    fi
    
    if [ $ERRORS -eq 0 ]; then
        log_success "Backup verification passed"
        return 0
    else
        log_error "Backup verification failed with $ERRORS error(s)"
        return 1
    fi
}

perform_backup() {
    log_info "Starting backup: $DATE"
    log_info "Backup directory: $BACKUP_DIR"
    
    # Create backup directory
    mkdir -p "$BACKUP_DIR"
    
    # Run backup steps
    backup_config
    backup_redis
    
    if [ $QUICK_MODE -eq 0 ]; then
        backup_chromadb
    else
        log_info "Skipping ChromaDB backup (quick mode)"
    fi
    
    backup_archives
    backup_logs
    create_manifest
    
    # Verify backup
    verify_backup
    
    # Calculate total backup size
    TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
    log_success "Backup completed: $TOTAL_SIZE"
    
    # Cleanup old backups
    cleanup_old_backups
    
    log_info "Backup location: $BACKUP_DIR"
}

restore_backup() {
    log_info "Restoring backup from: $RESTORE_DATE"
    
    RESTORE_PATH="$BACKUP_BASE_DIR/$RESTORE_DATE"
    
    if [ ! -d "$RESTORE_PATH" ]; then
        log_error "Backup not found: $RESTORE_PATH"
        exit 1
    fi
    
    log_warning "This will OVERWRITE current data. Press Ctrl+C to cancel..."
    sleep 5
    
    # Stop services
    log_info "Stopping services..."
    systemctl stop quantum-api telegram-bot || true
    
    # Restore Redis
    if [ -f "$RESTORE_PATH/redis-dump.rdb" ]; then
        log_info "Restoring Redis..."
        systemctl stop redis-server
        cp "$RESTORE_PATH/redis-dump.rdb" /var/lib/redis/dump.rdb
        systemctl start redis-server
        log_success "Redis restored"
    fi
    
    # Restore ChromaDB
    if [ -f "$RESTORE_PATH/chroma.tar.gz" ]; then
        log_info "Restoring ChromaDB..."
        rm -rf /memory/chroma
        tar -xzf "$RESTORE_PATH/chroma.tar.gz" -C /memory/
        log_success "ChromaDB restored"
    fi
    
    # Restore config
    if [ -f "$RESTORE_PATH/config/.env" ]; then
        log_info "Restoring .env..."
        cp "$RESTORE_PATH/config/.env" "$PROJECT_ROOT/.env"
        log_success ".env restored"
    fi
    
    # Restore archives
    if [ -f "$RESTORE_PATH/archives.tar.gz" ]; then
        log_info "Restoring archives..."
        mkdir -p "$PROJECT_ROOT/data"
        tar -xzf "$RESTORE_PATH/archives.tar.gz" -C "$PROJECT_ROOT/data/"
        log_success "Archives restored"
    fi
    
    # Restart services
    log_info "Starting services..."
    systemctl start quantum-api telegram-bot
    
    log_success "Restore completed!"
    log_info "Verify services: systemctl status quantum-api"
}

show_usage() {
    cat <<EOF
QuantumDev Backup Script

Usage:
  $0 [OPTIONS]

Options:
  --quick              Quick backup (skip ChromaDB)
  --restore <DATE>     Restore from backup (format: YYYYMMDD-HHMMSS)
  --list               List available backups
  --help               Show this help message

Examples:
  $0                           # Full backup
  $0 --quick                   # Quick backup
  $0 --restore 20251207-030000 # Restore backup
  $0 --list                    # List backups

EOF
}

list_backups() {
    log_info "Available backups:"
    echo ""
    
    if [ ! -d "$BACKUP_BASE_DIR" ]; then
        log_warning "No backups found (directory doesn't exist)"
        return
    fi
    
    COUNT=0
    for backup in "$BACKUP_BASE_DIR"/*; do
        if [ -d "$backup" ]; then
            BACKUP_NAME=$(basename "$backup")
            SIZE=$(du -sh "$backup" | cut -f1)
            echo "  $BACKUP_NAME ($SIZE)"
            COUNT=$((COUNT + 1))
        fi
    done
    
    if [ $COUNT -eq 0 ]; then
        log_warning "No backups found"
    else
        echo ""
        log_info "Total: $COUNT backup(s)"
    fi
}

# ============================================================
# MAIN
# ============================================================

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE=1
            shift
            ;;
        --restore)
            RESTORE_MODE=1
            RESTORE_DATE="$2"
            shift 2
            ;;
        --list)
            list_backups
            exit 0
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (sudo)"
    exit 1
fi

# Check dependencies
check_dependencies

# Execute mode
if [ $RESTORE_MODE -eq 1 ]; then
    restore_backup
else
    perform_backup
fi

log_success "Done!"
exit 0
