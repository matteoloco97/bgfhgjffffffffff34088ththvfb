#!/bin/bash

################################################################################
# Project Cleanup Script
# Purpose: Archive backup files, broken configs, and demo scripts
# Safety: Only moves files, never deletes
################################################################################

set -u  # Exit on undefined variable

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Generate timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Define archive directory
ARCHIVE_DIR="_archive/cleaned_${TIMESTAMP}"

# Counter for moved files
MOVED_COUNT=0

# Get script directory (repository root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

################################################################################
# Function: Create archive directory
################################################################################
create_archive_dir() {
    echo -e "${BLUE}[INFO]${NC} Creating archive directory: ${ARCHIVE_DIR}"
    mkdir -p "${SCRIPT_DIR}/${ARCHIVE_DIR}"
    echo -e "${GREEN}[SUCCESS]${NC} Archive directory created"
    echo ""
}

################################################################################
# Function: Move file to archive preserving directory structure
################################################################################
move_to_archive() {
    local source_file="$1"
    local relative_path="${source_file#./}"  # Remove leading ./
    local target_dir="${SCRIPT_DIR}/${ARCHIVE_DIR}/$(dirname "${relative_path}")"
    local target_file="${SCRIPT_DIR}/${ARCHIVE_DIR}/${relative_path}"
    
    # Create target directory if it doesn't exist
    mkdir -p "${target_dir}" || {
        echo -e "${RED}[ERROR]${NC} Failed to create directory: ${target_dir}"
        return 1
    }
    
    # Move the file
    if [ -f "${source_file}" ]; then
        if mv "${source_file}" "${target_file}" 2>/dev/null; then
            echo -e "${YELLOW}[MOVED]${NC} ${relative_path} -> ${ARCHIVE_DIR}/${relative_path}"
            ((MOVED_COUNT++))
        else
            echo -e "${RED}[ERROR]${NC} Failed to move: ${source_file}"
        fi
    else
        echo -e "${RED}[SKIP]${NC} File not found: ${source_file}"
    fi
}

################################################################################
# Main execution
################################################################################
main() {
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║         PROJECT CLEANUP - ARCHIVE OPERATION               ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Change to script directory
    cd "${SCRIPT_DIR}"
    
    # Create archive directory
    create_archive_dir
    
    echo -e "${BLUE}[INFO]${NC} Starting file archival process..."
    echo ""
    
    # Pattern 1: Files ending in .bak
    echo -e "${BLUE}[PATTERN]${NC} Searching for *.bak files..."
    while IFS= read -r -d '' file; do
        move_to_archive "$file"
    done < <(find . -type f -name "*.bak" -not -path "./_archive/*" -not -path "./.git/*" -print0 2>/dev/null)
    
    # Pattern 2: Files ending in .bak.*
    echo -e "${BLUE}[PATTERN]${NC} Searching for *.bak.* files..."
    while IFS= read -r -d '' file; do
        move_to_archive "$file"
    done < <(find . -type f -name "*.bak.*" -not -path "./_archive/*" -not -path "./.git/*" -print0 2>/dev/null)
    
    # Pattern 3: Files ending in .broken
    echo -e "${BLUE}[PATTERN]${NC} Searching for *.broken files..."
    while IFS= read -r -d '' file; do
        move_to_archive "$file"
    done < <(find . -type f -name "*.broken" -not -path "./_archive/*" -not -path "./.git/*" -print0 2>/dev/null)
    
    # Pattern 4: Files ending in .backup*
    echo -e "${BLUE}[PATTERN]${NC} Searching for *.backup* files..."
    while IFS= read -r -d '' file; do
        move_to_archive "$file"
    done < <(find . -type f -name "*.backup*" -not -path "./_archive/*" -not -path "./.git/*" -print0 2>/dev/null)
    
    # Pattern 5: Files ending in .old
    echo -e "${BLUE}[PATTERN]${NC} Searching for *.old files..."
    while IFS= read -r -d '' file; do
        move_to_archive "$file"
    done < <(find . -type f -name "*.old" -not -path "./_archive/*" -not -path "./.git/*" -print0 2>/dev/null)
    
    # Specific file 1: core/smart_search.pyy (typo file to be archived)
    echo -e "${BLUE}[SPECIFIC]${NC} Checking for core/smart_search.pyy..."
    if [ -f "core/smart_search.pyy" ]; then
        move_to_archive "./core/smart_search.pyy"
    fi
    
    # Specific file 2: core/a
    echo -e "${BLUE}[SPECIFIC]${NC} Checking for core/a..."
    if [ -f "core/a" ]; then
        move_to_archive "./core/a"
    fi
    
    # Pattern 6: Demo scripts in scripts/ starting with demo_
    echo -e "${BLUE}[PATTERN]${NC} Searching for scripts/demo_*.py files..."
    while IFS= read -r -d '' file; do
        move_to_archive "$file"
    done < <(find ./scripts -maxdepth 1 -type f -name "demo_*.py" -not -path "./_archive/*" -not -path "./.git/*" -print0 2>/dev/null)
    
    # Specific file 3: scripts/test_streaming_demo.py
    echo -e "${BLUE}[SPECIFIC]${NC} Checking for scripts/test_streaming_demo.py..."
    if [ -f "scripts/test_streaming_demo.py" ]; then
        move_to_archive "./scripts/test_streaming_demo.py"
    fi
    
    # Specific file 4: tests/manual_rate_limit_test.sh
    echo -e "${BLUE}[SPECIFIC]${NC} Checking for tests/manual_rate_limit_test.sh..."
    if [ -f "tests/manual_rate_limit_test.sh" ]; then
        move_to_archive "./tests/manual_rate_limit_test.sh"
    fi
    
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                    CLEANUP SUMMARY                        ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}[SUCCESS]${NC} Moved ${MOVED_COUNT} files to ${ARCHIVE_DIR}"
    echo -e "${GREEN}[INFO]${NC} Archive location: ${SCRIPT_DIR}/${ARCHIVE_DIR}"
    echo -e "${GREEN}[SAFE]${NC} No files were deleted - all files safely archived"
    echo ""
    
    if [ ${MOVED_COUNT} -eq 0 ]; then
        echo -e "${YELLOW}[NOTE]${NC} No files matched the cleanup criteria"
    fi
}

# Run main function
main

exit 0
