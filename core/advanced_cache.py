# core/advanced_cache.py - Enhanced cache with category-based TTL

import hashlib
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import redis
import json

log = logging.getLogger(__name__)

# ===================== ENVIRONMENT CONFIG =====================
# TTL configurabili per categoria (in secondi)
DEFAULT_TTL_HOURS = 6
CACHE_TTL_WEATHER = int(os.getenv("CACHE_TTL_WEATHER", "1800"))  # 30 min
CACHE_TTL_PRICE = int(os.getenv("CACHE_TTL_PRICE", "60"))  # 1 min
CACHE_TTL_SPORTS = int(os.getenv("CACHE_TTL_SPORTS", "300"))  # 5 min
CACHE_TTL_NEWS = int(os.getenv("CACHE_TTL_NEWS", "600"))  # 10 min
CACHE_TTL_SCHEDULE = int(os.getenv("CACHE_TTL_SCHEDULE", "3600"))  # 1 ora
CACHE_TTL_GENERIC = int(os.getenv("CACHE_TTL_GENERIC", "21600"))  # 6 ore

# Mapping categoria → TTL
CATEGORY_TTL_MAP = {
    "weather": CACHE_TTL_WEATHER,
    "price": CACHE_TTL_PRICE,
    "sports": CACHE_TTL_SPORTS,
    "news": CACHE_TTL_NEWS,
    "schedule": CACHE_TTL_SCHEDULE,
    "travel": CACHE_TTL_GENERIC,
    "health": CACHE_TTL_GENERIC,
    "code": CACHE_TTL_GENERIC,
    "generic": CACHE_TTL_GENERIC,
}


def get_ttl_for_category(category: str) -> int:
    """
    Restituisce il TTL appropriato per una categoria.
    
    Args:
        category: Categoria della query (weather, price, sports, etc.)
    
    Returns:
        TTL in secondi
    """
    return CATEGORY_TTL_MAP.get(category, CACHE_TTL_GENERIC)


class DomainCache:
    """
    Cache intelligente per domini già fetchati.
    Evita refetch dello stesso dominio in finestre temporali brevi.
    Supporta TTL differenti per categoria.
    """
    
    def __init__(self, redis_client, ttl_hours: int = DEFAULT_TTL_HOURS):
        self.redis = redis_client
        self.default_ttl_seconds = ttl_hours * 3600
    
    def _key(self, url: str, category: str = "generic") -> str:
        """Cache key basata su dominio+path+categoria."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        canonical = f"{parsed.netloc}{parsed.path}:{category}".lower()
        return f"domain_cache:{hashlib.md5(canonical.encode()).hexdigest()}"
    
    def get(self, url: str, category: str = "generic") -> Optional[Dict[str, Any]]:
        """
        Retrieve cached content per URL.
        
        Args:
            url: URL da cercare
            category: Categoria per determinare TTL
        """
        try:
            key = self._key(url, category)
            data = self.redis.get(key)
            if data:
                cached = json.loads(data)
                # Check se non expired (TTL gestito da Redis, questo è extra check)
                cached_time = datetime.fromisoformat(cached.get('cached_at', '2020-01-01'))
                ttl = get_ttl_for_category(category)
                if datetime.now() - cached_time < timedelta(seconds=ttl):
                    log.debug(f"Cache HIT: {url} (cat={category}, ttl={ttl}s)")
                    return cached
        except Exception as e:
            log.warning(f"Cache get error: {e}")
        return None
    
    def set(self, url: str, content: str, metadata: Dict = None, category: str = "generic"):
        """
        Cache content con TTL specifico per categoria.
        
        Args:
            url: URL da cachare
            content: Contenuto estratto
            metadata: Metadati aggiuntivi
            category: Categoria per determinare TTL
        """
        try:
            key = self._key(url, category)
            ttl = get_ttl_for_category(category)
            
            data = {
                "url": url,
                "content": content,
                "metadata": metadata or {},
                "category": category,
                "cached_at": datetime.now().isoformat()
            }
            self.redis.setex(
                key,
                ttl,
                json.dumps(data, ensure_ascii=False)
            )
            log.debug(f"Cache SET: {url} (cat={category}, ttl={ttl}s)")
        except Exception as e:
            log.warning(f"Cache set error: {e}")
    
    def bulk_check(self, urls: List[str], category: str = "generic") -> Dict[str, Optional[Dict]]:
        """
        Check multiple URLs at once (pipeline).
        
        Args:
            urls: Lista di URL da controllare
            category: Categoria per tutti gli URL
        """
        result = {}
        try:
            pipe = self.redis.pipeline()
            keys = []
            for url in urls:
                key = self._key(url, category)
                keys.append((url, key))
                pipe.get(key)
            
            responses = pipe.execute()
            ttl = get_ttl_for_category(category)
            
            for (url, key), data in zip(keys, responses):
                if data:
                    try:
                        cached = json.loads(data)
                        cached_time = datetime.fromisoformat(cached.get('cached_at', '2020-01-01'))
                        if datetime.now() - cached_time < timedelta(seconds=ttl):
                            result[url] = cached
                            continue
                    except Exception:
                        pass
                result[url] = None
        except Exception as e:
            log.warning(f"Cache bulk_check error: {e}")
        
        return result
    
    def invalidate(self, url: str, category: str = "generic") -> bool:
        """
        Invalida manualmente una entry cache.
        
        Args:
            url: URL da invalidare
            category: Categoria
        
        Returns:
            True se invalidato, False altrimenti
        """
        try:
            key = self._key(url, category)
            deleted = self.redis.delete(key)
            return deleted > 0
        except Exception as e:
            log.warning(f"Cache invalidate error: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Statistiche cache (per debug/monitoring).
        """
        try:
            # Conta chiavi per pattern
            keys = list(self.redis.scan_iter("domain_cache:*"))
            return {
                "total_entries": len(keys),
                "ttl_config": CATEGORY_TTL_MAP,
            }
        except Exception as e:
            return {"error": str(e)}


class QueryCache:
    """
    Cache per risultati di query complete.
    Usata per cachare risultati di ricerche web già elaborate.
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def _key(self, query: str, category: str = "generic") -> str:
        """Cache key basata su query + categoria."""
        q_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16]
        return f"query_cache:{category}:{q_hash}"
    
    def get(self, query: str, category: str = "generic") -> Optional[Dict[str, Any]]:
        """Recupera risultato query cachato."""
        try:
            key = self._key(query, category)
            data = self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            log.warning(f"QueryCache get error: {e}")
        return None
    
    def set(self, query: str, result: Dict[str, Any], category: str = "generic"):
        """Salva risultato query."""
        try:
            key = self._key(query, category)
            ttl = get_ttl_for_category(category)
            
            data = {
                "query": query,
                "result": result,
                "category": category,
                "cached_at": datetime.now().isoformat()
            }
            self.redis.setex(key, ttl, json.dumps(data, ensure_ascii=False))
        except Exception as e:
            log.warning(f"QueryCache set error: {e}")


# ===================== FETCH WITH CACHE =====================

async def _fetch_one_with_cache(
    item: Dict[str, Any],
    budget: int,
    index: int,
    domain_cache: DomainCache,
    category: str = "generic"  # Default mantiene backward compatibility
) -> Optional[Dict[str, Any]]:
    """
    Fetch con cache integrata e categoria.
    
    Args:
        item: Dict con url e title
        budget: Token budget per trimming
        index: Indice risultato
        domain_cache: Istanza DomainCache
        category: Categoria per TTL
    """
    url = item.get("url", "")
    
    # Check cache PRIMA di fetch
    cached = domain_cache.get(url, category)
    if cached and cached.get('content'):
        log.info(f"✓ Cache HIT: {url} (cat={category})")
        try:
            from core.token_budget import trim_to_tokens
            trimmed = trim_to_tokens(cached['content'], budget)
        except Exception:
            trimmed = cached['content'][:budget * 4]
        
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
        from core.web_tools import fetch_and_extract_robust
        text, og_img = await fetch_and_extract_robust(url, timeout=6.0)
        
        if text and len(text) > 100:
            # Salva in cache
            domain_cache.set(url, text, {"og_image": og_img}, category)
            
            try:
                from core.token_budget import trim_to_tokens
                trimmed = trim_to_tokens(text, budget)
            except Exception:
                trimmed = text[:budget * 4]
            
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
