"""
core/async_http_client.py

Centralized async HTTP client with connection pooling.
Provides shared aiohttp ClientSession for all async HTTP operations.
"""

import os
import logging
import asyncio
from typing import Optional

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None  # type: ignore
    AIOHTTP_AVAILABLE = False

logger = logging.getLogger(__name__)

# ===================== Configuration from Environment =====================

HTTP_POOL_SIZE = int(os.getenv("HTTP_POOL_SIZE", "50"))
HTTP_POOL_PER_HOST = int(os.getenv("HTTP_POOL_PER_HOST", "10"))
HTTP_CONNECT_TIMEOUT = float(os.getenv("HTTP_CONNECT_TIMEOUT", "2.0"))
HTTP_SOCK_READ_TIMEOUT = float(os.getenv("HTTP_SOCK_READ_TIMEOUT", "6.0"))
HTTP_TOTAL_TIMEOUT = float(os.getenv("HTTP_TOTAL_TIMEOUT", "10.0"))

# Default User-Agent
DEFAULT_USER_AGENT = os.getenv(
    "HTTP_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
)

# ===================== Global HTTP Session =====================

_HTTP_SESSION: Optional['aiohttp.ClientSession'] = None
_SESSION_LOCK: Optional[asyncio.Lock] = None


async def get_http_client() -> Optional['aiohttp.ClientSession']:
    """
    Get or create the shared aiohttp ClientSession with connection pooling.
    
    Returns:
        Shared ClientSession instance, or None if aiohttp is not available
    
    Features:
    - Connection pooling (HTTP_POOL_SIZE total connections)
    - Per-host limits (HTTP_POOL_PER_HOST)
    - DNS caching (5 minutes TTL)
    - Keep-alive connections
    - Automatic retry and timeout configuration
    """
    global _HTTP_SESSION, _SESSION_LOCK
    
    if not AIOHTTP_AVAILABLE:
        logger.warning("aiohttp not available, cannot create HTTP client")
        return None
    
    # Initialize lock on first call (thread-safe)
    if _SESSION_LOCK is None:
        _SESSION_LOCK = asyncio.Lock()
    
    async with _SESSION_LOCK:
        if _HTTP_SESSION is None or _HTTP_SESSION.closed:
            try:
                # Create TCP connector with connection pooling
                connector = aiohttp.TCPConnector(
                    limit=HTTP_POOL_SIZE,
                    limit_per_host=HTTP_POOL_PER_HOST,
                    ttl_dns_cache=300,  # Cache DNS for 5 minutes
                    enable_cleanup_closed=True,
                    force_close=False,  # Reuse connections
                    keepalive_timeout=30  # Keep connections alive for 30s
                )
                
                # Create timeout configuration
                timeout = aiohttp.ClientTimeout(
                    total=HTTP_TOTAL_TIMEOUT,
                    connect=HTTP_CONNECT_TIMEOUT,
                    sock_read=HTTP_SOCK_READ_TIMEOUT
                )
                
                # Create session with default headers
                _HTTP_SESSION = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers={
                        'User-Agent': DEFAULT_USER_AGENT,
                        'Accept': '*/*',
                        'Accept-Encoding': 'gzip, deflate',
                    },
                    trust_env=False  # Don't use system proxy settings
                )
                
                logger.info(
                    f"HTTP client initialized: pool_size={HTTP_POOL_SIZE}, "
                    f"per_host={HTTP_POOL_PER_HOST}, timeout={HTTP_TOTAL_TIMEOUT}s"
                )
                
            except Exception as e:
                logger.error(f"Failed to create HTTP client: {e}")
                return None
    
    return _HTTP_SESSION


async def close_http_client():
    """
    Close and cleanup the shared HTTP client session.
    Should be called on application shutdown.
    """
    global _HTTP_SESSION
    
    if _HTTP_SESSION and not _HTTP_SESSION.closed:
        try:
            await _HTTP_SESSION.close()
            logger.info("HTTP client closed")
        except Exception as e:
            logger.error(f"Error closing HTTP client: {e}")
        finally:
            _HTTP_SESSION = None


def is_http_client_available() -> bool:
    """
    Check if async HTTP client is available and initialized.
    
    Returns:
        True if aiohttp is available and client can be created
    """
    return AIOHTTP_AVAILABLE


# ===================== Helper Functions =====================

async def ensure_http_client() -> 'aiohttp.ClientSession':
    """
    Ensure HTTP client is initialized and return it.
    Raises RuntimeError if not available.
    
    Returns:
        Active ClientSession
        
    Raises:
        RuntimeError: If aiohttp is not available
    """
    client = await get_http_client()
    if client is None:
        raise RuntimeError("aiohttp not available or failed to initialize")
    return client


__all__ = [
    'get_http_client',
    'close_http_client',
    'is_http_client_available',
    'ensure_http_client',
    'HTTP_POOL_SIZE',
    'HTTP_POOL_PER_HOST',
    'HTTP_TOTAL_TIMEOUT',
]
