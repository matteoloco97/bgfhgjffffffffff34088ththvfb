#!/bin/bash
# ============================================================================
# QuantumDev - Docker Build Script
# Builds all Docker images with proper tagging
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REGISTRY="${DOCKER_REGISTRY:-}"
TAG="${DOCKER_TAG:-latest}"
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
VCS_REF=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# Image names
API_IMAGE="quantumdev-api"
BOT_IMAGE="quantumdev-telegram-bot"
WORKER_IMAGE="quantumdev-worker"

# Build arguments
BUILD_ARGS=(
    --build-arg "BUILD_DATE=${BUILD_DATE}"
    --build-arg "VCS_REF=${VCS_REF}"
)

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
    echo "  QuantumDev Docker Build"
    echo "  Tag: ${TAG}"
    echo "  Date: ${BUILD_DATE}"
    echo "  Commit: ${VCS_REF}"
    echo "============================================"
    echo ""
}

build_image() {
    local image_name=$1
    local dockerfile=$2
    local full_name="${image_name}:${TAG}"
    
    if [ -n "${REGISTRY}" ]; then
        full_name="${REGISTRY}/${full_name}"
    fi
    
    log_info "Building ${full_name}..."
    
    docker build \
        "${BUILD_ARGS[@]}" \
        -f "${dockerfile}" \
        -t "${full_name}" \
        .
    
    if [ $? -eq 0 ]; then
        log_success "Built ${full_name}"
        
        # Also tag as latest if building a specific version
        if [ "${TAG}" != "latest" ]; then
            docker tag "${full_name}" "${image_name}:latest"
            log_info "Also tagged as ${image_name}:latest"
        fi
    else
        log_error "Failed to build ${full_name}"
        return 1
    fi
}

show_usage() {
    echo "Usage: $0 [OPTIONS] [TARGETS]"
    echo ""
    echo "Options:"
    echo "  -t, --tag TAG       Tag for images (default: latest)"
    echo "  -r, --registry REG  Docker registry prefix"
    echo "  --no-cache          Build without cache"
    echo "  --push              Push images after building"
    echo "  -h, --help          Show this help"
    echo ""
    echo "Targets:"
    echo "  all     Build all images (default)"
    echo "  api     Build API image only"
    echo "  bot     Build Telegram bot image only"
    echo "  worker  Build worker image only"
    echo ""
    echo "Examples:"
    echo "  $0                          # Build all with 'latest' tag"
    echo "  $0 -t v1.0.0                # Build all with 'v1.0.0' tag"
    echo "  $0 api bot                  # Build only API and bot"
    echo "  $0 --push -t v1.0.0 all     # Build and push all"
}

# Parse arguments
NO_CACHE=""
PUSH_AFTER=""
TARGETS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            BUILD_ARGS+=("$NO_CACHE")
            shift
            ;;
        --push)
            PUSH_AFTER="true"
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            TARGETS+=("$1")
            shift
            ;;
    esac
done

# Default to all targets
if [ ${#TARGETS[@]} -eq 0 ]; then
    TARGETS=("all")
fi

# Main execution
print_header

# Change to script directory
cd "$(dirname "$0")/.."

# Build requested targets
for target in "${TARGETS[@]}"; do
    case $target in
        all)
            build_image "${API_IMAGE}" "Dockerfile"
            build_image "${BOT_IMAGE}" "Dockerfile.bot"
            build_image "${WORKER_IMAGE}" "Dockerfile.worker"
            ;;
        api)
            build_image "${API_IMAGE}" "Dockerfile"
            ;;
        bot)
            build_image "${BOT_IMAGE}" "Dockerfile.bot"
            ;;
        worker)
            build_image "${WORKER_IMAGE}" "Dockerfile.worker"
            ;;
        *)
            log_error "Unknown target: ${target}"
            show_usage
            exit 1
            ;;
    esac
done

# Push if requested
if [ -n "${PUSH_AFTER}" ]; then
    if [ -z "${REGISTRY}" ]; then
        log_error "Cannot push: REGISTRY not set. Use -r/--registry to specify a registry."
        exit 1
    fi
    
    log_info "Pushing images to registry ${REGISTRY}..."
    
    for target in "${TARGETS[@]}"; do
        case $target in
            all)
                docker push "${REGISTRY}/${API_IMAGE}:${TAG}"
                docker push "${REGISTRY}/${BOT_IMAGE}:${TAG}"
                docker push "${REGISTRY}/${WORKER_IMAGE}:${TAG}"
                ;;
            api)
                docker push "${REGISTRY}/${API_IMAGE}:${TAG}"
                ;;
            bot)
                docker push "${REGISTRY}/${BOT_IMAGE}:${TAG}"
                ;;
            worker)
                docker push "${REGISTRY}/${WORKER_IMAGE}:${TAG}"
                ;;
        esac
    done
    
    log_success "All images pushed to ${REGISTRY}"
fi

# Show built images
echo ""
log_info "Built images:"
docker images | grep -E "quantumdev-(api|telegram-bot|worker)" | head -10

echo ""
log_success "Build completed successfully!"
