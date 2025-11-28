#!/usr/bin/env python3
"""
robust_content_extraction.py
============================
Multi-strategy content extraction per QuantumDev
"""

import re
import logging
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    log.warning("BeautifulSoup not available")

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

try:
    from readability import Document
    HAS_READABILITY = True
except ImportError:
    HAS_READABILITY = False


def extract_ilmeteo(html: str) -> Optional[str]:
    """Extractor per ilmeteo.it - usa html.parser per evitare XML errors"""
    if not HAS_BS4:
        return None
    
    try:
        # FIX: html.parser invece di lxml (più permissivo con caratteri invalidi)
        soup = BeautifulSoup(html, 'html.parser')
        parts = []
        
        # Cerca temperature
        temp_elements = soup.find_all(string=re.compile(r'\d+\s*°[CF]', re.I))
        temps = []
        for elem in temp_elements[:10]:
            text = elem.strip()
            if len(text) < 50:
                temps.append(text)
        
        if temps:
            parts.append("🌡️ " + ", ".join(set(temps)))
        
        # Containers meteo
        meteo_containers = soup.find_all(['div', 'section', 'article'], 
                                        class_=re.compile(r'(meteo|weather|forecast|prev)', re.I))
        for container in meteo_containers[:3]:
            text = container.get_text(separator=' ', strip=True)
            if any(kw in text.lower() for kw in ['temperatura', 'cielo', 'vento', '°c', 'pioggia']):
                parts.append(text[:300])
        
        # Paragrafi con keywords
        paragraphs = soup.find_all('p')
        for p in paragraphs[:15]:
            text = p.get_text(strip=True)
            if (len(text) > 30 and 
                any(k in text.lower() for k in ['temperatura', 'meteo', '°c', 'cielo', 'previsioni', 'vento'])):
                parts.append(text)
        
        # Headers località
        headers = soup.find_all(['h1', 'h2', 'h3'])
        for h in headers[:5]:
            text = h.get_text(strip=True)
            if 'roma' in text.lower() or 'meteo' in text.lower():
                parts.insert(0, f"📍 {text}")
        
        if parts:
            result = "\n\n".join(parts[:10])
            log.info(f"✅ IlMeteo specialty handler: {len(result)} chars")
            return result
        
    except Exception as e:
        log.warning(f"ilmeteo handler error: {e}")
    
    return None


def extract_3bmeteo(html: str) -> Optional[str]:
    if not HAS_BS4:
        return None
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        parts = []
        
        forecast = soup.find(class_=re.compile(r'(forecast|previsione)', re.I))
        if forecast:
            parts.append(forecast.get_text(separator='\n', strip=True)[:500])
        
        temps = soup.find_all(string=re.compile(r'\d+°'))
        if temps:
            parts.append("Temp: " + ", ".join(t.strip() for t in temps[:6]))
        
        descriptions = soup.find_all(['p', 'div'], limit=10)
        for desc in descriptions:
            text = desc.get_text(strip=True)
            if len(text) > 40 and 'meteo' in text.lower():
                parts.append(text)
        
        return "\n".join(parts) if parts else None
        
    except Exception as e:
        log.warning(f"3bmeteo error: {e}")
    return None


def extract_meteoam(html: str) -> Optional[str]:
    if not HAS_BS4:
        return None
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        main = soup.find(['article', 'main'])
        if main:
            return main.get_text(separator='\n', strip=True)[:800]
        
        paragraphs = soup.find_all('p')
        texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50]
        return "\n\n".join(texts[:5]) if texts else None
        
    except Exception as e:
        log.warning(f"meteoam error: {e}")
    return None


DOMAIN_HANDLERS = {
    "ilmeteo.it": extract_ilmeteo,
    "www.ilmeteo.it": extract_ilmeteo,
    "3bmeteo.com": extract_3bmeteo,
    "www.3bmeteo.com": extract_3bmeteo,
    "meteoam.it": extract_meteoam,
    "www.meteoam.it": extract_meteoam,
}


def extract_with_trafilatura(html: str) -> Optional[str]:
    if not HAS_TRAFILATURA:
        return None
    
    try:
        text = trafilatura.extract(html, include_comments=False, include_tables=True, no_fallback=False)
        return text if text and len(text) > 100 else None
    except Exception as e:
        log.debug(f"Trafilatura failed: {e}")
    return None


def extract_with_readability(html: str) -> Optional[str]:
    if not HAS_READABILITY or not HAS_BS4:
        return None
    
    try:
        doc = Document(html)
        soup = BeautifulSoup(doc.summary(), 'html.parser')
        text = soup.get_text(separator="\n", strip=True)
        return text if text and len(text) > 100 else None
    except Exception as e:
        log.debug(f"Readability failed: {e}")
    return None


def extract_aggressive(html: str) -> Optional[str]:
    if not HAS_BS4:
        return None
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        parts = []
        
        title = soup.find('h1')
        if title:
            parts.append(f"# {title.get_text(strip=True)}")
        
        main = soup.find(['article', 'main', 'div'], class_=re.compile(r'(content|main|article)', re.I))
        if main:
            for p in main.find_all(['p', 'div', 'li'])[:20]:
                text = p.get_text(strip=True)
                if len(text) > 30:
                    parts.append(text)
        else:
            for p in soup.find_all('p')[:15]:
                text = p.get_text(strip=True)
                if len(text) > 40:
                    parts.append(text)
        
        result = "\n\n".join(parts)
        return result if len(result) > 150 else None
        
    except Exception as e:
        log.warning(f"Aggressive parsing failed: {e}")
    return None


def extract_metadata_fallback(html: str) -> Optional[str]:
    if not HAS_BS4:
        return None
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        parts = []
        
        title = soup.find("title")
        if title:
            parts.append(title.get_text(strip=True))
        
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            parts.append(meta_desc["content"])
        
        pars = soup.find_all('p')[:10]
        for p in pars:
            text = p.get_text(strip=True)
            if len(text) > 30:
                parts.append(text)
        
        return "\n\n".join(parts) if parts else None
        
    except Exception as e:
        log.warning(f"Metadata fallback failed: {e}")
    return None


def extract_content_robust(html: str, url: str) -> str:
    """Multi-strategy extraction con 5 livelli di fallback"""
    
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
    except:
        domain = ""
    
    # STRATEGY 1: Domain handler
    if domain in DOMAIN_HANDLERS:
        result = DOMAIN_HANDLERS[domain](html)
        if result:
            return result
    
    # STRATEGY 2: Trafilatura
    result = extract_with_trafilatura(html)
    if result:
        log.info(f"✅ Trafilatura: {url}")
        return result
    
    # STRATEGY 3: Readability
    result = extract_with_readability(html)
    if result:
        log.info(f"✅ Readability: {url}")
        return result
    
    # STRATEGY 4: Aggressive
    result = extract_aggressive(html)
    if result:
        log.info(f"✅ Aggressive: {url}")
        return result
    
    # STRATEGY 5: Metadata
    result = extract_metadata_fallback(html)
    if result:
        log.warning(f"⚠️ Metadata: {url}")
        return result
    
    # ABSOLUTE FALLBACK
    if HAS_BS4:
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text)
        if len(text) > 100:
            log.warning(f"⚠️ Plain text: {url}")
            return text[:2000]
    
    return f"[Contenuto non disponibile: {url}]"
