#!/bin/bash
# QuantumDev deprecated files cleanup (Phase 2 - Priority 8)
# Creates backup before removing deprecated files and consolidates documentation

set -e

PROJECT_ROOT="/home/runner/work/bgfhgjffffffffff34088ththvfb/bgfhgjffffffffff34088ththvfb/Contabo VPS/quantumdev-open"
BACKUP_DIR="/tmp/quantumdev_cleanup_backup_$(date +%Y%m%d_%H%M%S)"

echo "🧹 QuantumDev Cleanup - Phase 2"
echo "================================"
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Backup location: $BACKUP_DIR"
echo ""

# Create backup directory
echo "📦 Creating backup directory..."
mkdir -p "$BACKUP_DIR"

cd "$PROJECT_ROOT" || exit 1

# Function to backup and remove file
backup_and_remove() {
    local file="$1"
    if [ -f "$file" ]; then
        echo "  Backing up: $file"
        cp "$file" "$BACKUP_DIR/" 2>/dev/null || true
        rm -f "$file"
        echo "  ✅ Removed: $file"
    fi
}

# Backup deprecated files
echo ""
echo "📄 Backing up deprecated files..."

backup_and_remove "agents/backup.py"
backup_and_remove "IMPLEMENTATION_COMPLETE.md"
backup_and_remove "IMPLEMENTATION_SUMMARY.md"
backup_and_remove "SESSION_SUMMARY.md"
backup_and_remove "PERSONA_CLEANUP_SUMMARY.md"

# Also backup any other session/implementation summaries
for file in IMPLEMENTATION_*.md SESSION_*.md; do
    if [ -f "$file" ]; then
        backup_and_remove "$file"
    fi
done

echo ""
echo "📝 Consolidating documentation..."

# Create CHANGELOG.md with Phase 2 information
cat > CHANGELOG.md << 'EOF'
# QuantumDev Changelog

## v4.2 - Phase 2 Performance Optimizations (2025-12-17)

### Web Parallelization
- Added global aiohttp session with connection pooling (`HTTP_POOL_SIZE=50`, `HTTP_POOL_PER_HOST=10`)
- Improved async HTTP performance with TCPConnector and ClientTimeout
- Added `get_http_session()` and `close_http_session()` for lifecycle management

### Multi-Level Cache System
- Implemented L1 in-memory LRU cache (100 items, <1ms latency)
- Integrated with existing L2 Redis semantic cache
- Added cache statistics and monitoring endpoints
- Configurable via `ENABLE_L1_CACHE`, `L1_CACHE_SIZE`, `L1_CACHE_TTL`

### Code Quality
- Removed deprecated files and consolidated documentation
- Updated .gitignore with deprecated file patterns
- Improved logging and error handling

---

## v4.1 - Phase 1 Optimizations (2024-12)

### Memory System
- Memory retrieval fix (+25% accuracy: 45% → 70%)
- Extended memory retention (30 days short-term, 2 years long-term)

### Performance
- Reasoning traces optimization (99.7% overhead reduction)
- Semantic context pruning (30-50% efficiency gain)

### Features
- Italian NLP module (grammar correction)
- Proactive suggestions enabled
- Context window: 32K → 65K

---

## v4.0 - Base Improvements (2024-11)

### Core Features
- Context window expansion to 32K tokens
- Memory retention extended to 30 days / 2 years
- Cache hit rate optimization (85%+ threshold)
- Proactive suggestions system

### Infrastructure
- Redis integration for caching
- ChromaDB for vector memory
- Multi-provider web search (DDG, Bing, SerpAPI, Google)

---

## Previous Versions

See git history for details of versions prior to v4.0.

EOF

echo "✅ Created CHANGELOG.md"

# Update .gitignore
echo ""
echo "🚫 Updating .gitignore..."

# Append to .gitignore if it exists, otherwise create it
if [ ! -f .gitignore ]; then
    touch .gitignore
fi

# Check if patterns already exist
if ! grep -q "# Backup files" .gitignore 2>/dev/null; then
    cat >> .gitignore << 'EOF'

# Backup files
*.backup-*
*_backup_*
*.old

# Deprecated docs
IMPLEMENTATION_*.md
SESSION_SUMMARY.md
PERSONA_CLEANUP_SUMMARY.md

EOF
    echo "✅ Updated .gitignore"
else
    echo "  ℹ️  .gitignore already has cleanup patterns"
fi

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "Summary:"
echo "  📦 Backup location: $BACKUP_DIR"
echo "  📝 Created: CHANGELOG.md"
echo "  🚫 Updated: .gitignore"
echo ""
echo "ℹ️  To restore files, copy from: $BACKUP_DIR"
