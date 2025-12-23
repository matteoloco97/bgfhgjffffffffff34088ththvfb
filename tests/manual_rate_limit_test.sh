#!/bin/bash

# Manual Test Script for Rate Limiting
# This script demonstrates how to test the rate limiting implementation

echo "======================================================================"
echo "Rate Limiting Manual Test Script"
echo "======================================================================"
echo ""
echo "Prerequisites:"
echo "  1. Redis must be running (redis-server)"
echo "  2. FastAPI backend must be running (uvicorn backend.quantum_api:app)"
echo "  3. curl or httpie installed for making requests"
echo ""
echo "======================================================================"
echo ""

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-your-secure-admin-token-here}"

echo "Using API URL: $API_URL"
echo ""

# Test 1: Chat endpoint rate limiting (10 req/min)
echo "Test 1: /chat endpoint (10 requests/minute)"
echo "----------------------------------------------------------------------"
echo "Making 11 requests to /chat from external IP..."
echo ""

for i in {1..11}; do
    echo -n "Request $i: "
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/chat" \
        -H "Content-Type: application/json" \
        -H "X-Forwarded-For: 203.0.113.1" \
        -d '{"text": "test message '$i'", "source": "test", "source_id": "test_user"}')
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    
    if [ "$HTTP_CODE" == "429" ]; then
        echo "✓ RATE LIMITED (429) - Expected after 10 requests"
    elif [ "$i" -le 10 ]; then
        echo "✓ OK ($HTTP_CODE) - Within limit"
    else
        echo "✗ FAILED - Should be rate limited but got $HTTP_CODE"
    fi
    
    sleep 0.5
done

echo ""

# Test 2: Localhost bypass
echo "Test 2: Localhost bypass (127.0.0.1 should NEVER be rate limited)"
echo "----------------------------------------------------------------------"
echo "Making 15 requests from localhost..."
echo ""

for i in {1..15}; do
    echo -n "Request $i: "
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/chat" \
        -H "Content-Type: application/json" \
        -d '{"text": "localhost test '$i'", "source": "telegram", "source_id": "bot"}')
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    
    if [ "$HTTP_CODE" == "429" ]; then
        echo "✗ FAILED - Localhost should NEVER be rate limited!"
    else
        echo "✓ OK ($HTTP_CODE) - Localhost bypass working"
    fi
    
    sleep 0.5
done

echo ""

# Test 3: Admin token bypass
echo "Test 3: Admin token bypass"
echo "----------------------------------------------------------------------"
echo "Making 15 requests with admin token from external IP..."
echo ""

for i in {1..15}; do
    echo -n "Request $i: "
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/autonomous" \
        -H "Content-Type: application/json" \
        -H "X-Admin-Token: $ADMIN_TOKEN" \
        -H "X-Forwarded-For: 203.0.113.2" \
        -d '{"goal": "admin test '$i'", "source": "api", "source_id": "admin"}')
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    
    if [ "$HTTP_CODE" == "429" ]; then
        echo "✗ FAILED - Admin token bypass should work!"
    else
        echo "✓ OK ($HTTP_CODE) - Admin bypass working"
    fi
    
    sleep 0.5
done

echo ""

# Test 4: Different endpoints have different limits
echo "Test 4: Different endpoints have different limits"
echo "----------------------------------------------------------------------"
echo ""

echo "Testing /web/search (20 req/min)..."
for i in {1..21}; do
    echo -n "Request $i: "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/web/search" \
        -H "Content-Type: application/json" \
        -H "X-Forwarded-For: 203.0.113.3" \
        -d '{"q": "test query '$i'", "source": "test", "source_id": "test_user"}')
    
    if [ "$HTTP_CODE" == "429" ]; then
        echo "✓ RATE LIMITED (429) - Expected after 20 requests"
        break
    elif [ "$i" -le 20 ]; then
        echo "✓ OK ($HTTP_CODE)"
    else
        echo "✗ FAILED - Should be rate limited"
    fi
    
    sleep 0.5
done

echo ""
echo "Testing /autonomous (5 req/min)..."
for i in {1..6}; do
    echo -n "Request $i: "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/autonomous" \
        -H "Content-Type: application/json" \
        -H "X-Forwarded-For: 203.0.113.4" \
        -d '{"goal": "test goal '$i'", "source": "test", "source_id": "test_user"}')
    
    if [ "$HTTP_CODE" == "429" ]; then
        echo "✓ RATE LIMITED (429) - Expected after 5 requests"
        break
    elif [ "$i" -le 5 ]; then
        echo "✓ OK ($HTTP_CODE)"
    else
        echo "✗ FAILED - Should be rate limited"
    fi
    
    sleep 0.5
done

echo ""

# Test 5: Check 429 error format and headers
echo "Test 5: Check 429 error response format and headers"
echo "----------------------------------------------------------------------"
echo ""

echo "Triggering rate limit and checking response..."

# First, hit the limit
for i in {1..10}; do
    curl -s -o /dev/null -X POST "$API_URL/chat" \
        -H "Content-Type: application/json" \
        -H "X-Forwarded-For: 203.0.113.5" \
        -d '{"text": "test '$i'", "source": "test", "source_id": "test_user"}'
    sleep 0.1
done

# Now get the 429 response
echo "Full 429 response:"
curl -v -X POST "$API_URL/chat" \
    -H "Content-Type: application/json" \
    -H "X-Forwarded-For: 203.0.113.5" \
    -d '{"text": "test", "source": "test", "source_id": "test_user"}' 2>&1 | grep -E "(HTTP/|X-RateLimit|Retry-After|error|retry_after)"

echo ""
echo "======================================================================"
echo "Manual test script completed"
echo "======================================================================"
echo ""
echo "Expected behavior:"
echo "  ✓ External IPs are rate limited according to per-endpoint limits"
echo "  ✓ Localhost (127.0.0.1) is NEVER rate limited"
echo "  ✓ Admin token bypasses rate limits"
echo "  ✓ 429 responses include proper error messages and headers"
echo "  ✓ Different IPs have independent rate limits"
echo ""
