# core/advanced_cache.py - NEW FILE

import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import redis
import json

class DomainCache:
    """
    Cache intelligente per domini già fetchati.
    Evita refetch dello stesso dominio in finestre temporali brevi.
    """
    
    def __init__(self, redis_client, ttl_hours: int = 6):
        self.redis = redis_client
        self.ttl_seconds = ttl_hours * 3600
    
    def _key(self, url: str) -> str:
        """Cache key basata su dominio+path (no query params)."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        canonical = f"{parsed.netloc}{parsed.path}".lower()
        return f"domain_cache:{hashlib.md5(canonical.encode()).hexdigest()}"
    
    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached content per URL."""
        try:
            key = self._key(url)
            data = self.redis.get(key)
            if data:
                cached = json.loads(data)
                # Check se non expired manualmente
                cached_time = datetime.fromisoformat(cached.get('cached_at', '2020-01-01'))
                if datetime.now() - cached_time < timedelta(seconds=self.ttl_seconds):
                    return cached
        except Exception:
            pass
        return None
    
    def set(self, url: str, content: str, metadata: Dict = None):
        """Cache content."""
        try:
            key = self._key(url)
            data = {
                "url": url,
                "content": content,
                "metadata": metadata or {},
                "cached_at": datetime.now().isoformat()
            }
            self.redis.setex(
                key,
                self.ttl_seconds,
                json.dumps(data, ensure_ascii=False)
            )
        except Exception:
            pass
    
    def bulk_check(self, urls: List[str]) -> Dict[str, Optional[Dict]]:
        """Check multiple URLs at once (pipeline)."""
        result = {}
        try:
            pipe = self.redis.pipeline()
            keys = []
            for url in urls:
                key = self._key(url)
                keys.append((url, key))
                pipe.get(key)
            
            responses = pipe.execute()
            
            for (url, key), data in zip(keys, responses):
                if data:
                    try:
                        cached = json.loads(data)
                        cached_time = datetime.fromisoformat(cached.get('cached_at', '2020-01-01'))
                        if datetime.now() - cached_time < timedelta(seconds=self.ttl_seconds):
                            result[url] = cached
                            continue
                    except Exception:
                        pass
                result[url] = None
        except Exception:
            pass
        
        return result


# Integrazione nel fetch pipeline
async def _fetch_one_with_cache(
    item: Dict[str, Any],
    budget: int,
    index: int,
    domain_cache: DomainCache
) -> Optional[Dict[str, Any]]:
    url = item.get("url", "")
    
    # Check cache PRIMA di fetch
    cached = domain_cache.get(url)
    if cached and cached.get('content'):
        log.info(f"✓ Cache HIT: {url}")
        from core.token_budget import trim_to_tokens
        trimmed = trim_to_tokens(cached['content'], budget)
        return {
            "url": url,
            "title": item.get('title', url),
            "text": trimmed,
            "og_image": cached.get('metadata', {}).get('og_image'),
            "budget_used": len(trimmed) // 4,
            "index": index,
            "cached": True
        }
    
    # Altrimenti fetch normale
    try:
        text, og_img = await fetch_and_extract_robust(url, timeout=6.0)
        
        if text and len(text) > 100:
            # Salva in cache
            domain_cache.set(url, text, {"og_image": og_img})
            
            trimmed = trim_to_tokens(text, budget)
            return {
                "url": url,
                "title": item.get('title', url),
                "text": trimmed,
                "og_image": og_img,
                "budget_used": len(trimmed) // 4,
                "index": index,
                "cached": False
            }
    except Exception as e:
        log.warning(f"Fetch error: {url} - {e}")
    
    return None
