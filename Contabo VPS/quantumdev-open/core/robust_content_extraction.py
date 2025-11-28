#!/usr/bin/env python3
"""
robust_content_extraction.py
=============================
Extraction multi-strategy AGGRESSIVA per estrarre SEMPRE contenuto utile.

PROBLEMA ATTUALE:
- fetch_and_extract() fallisce su siti JavaScript-heavy (meteo, news)
- Trafilatura/Readability non funzionano su tutti i siti
- Fallback troppo deboli → torna stringa vuota

SOLUZIONE:
- 5 strategie di extraction in cascata
- Specialty handlers per domini specifici (ilmeteo.it, 3bmeteo.com, etc.)
- Metadata extraction come ultimo resort
- SEMPRE ritorna QUALCOSA di utile

GUADAGNO ATTESO:
- Content extraction success: da ~60% a ~95%
- Combinato con synthesis aggressiva → risposta utile anche con partial data
"""

import re
import logging
from typing import Tuple, Optional, Dict, Any, List
from bs4 import BeautifulSoup, Comment

log = logging.getLogger(__name__)


# ==================== SPECIALTY HANDLERS ====================

class SpecialtyExtractor:
    """
    Handler specifici per domini problematici.
    Conoscenza domain-specific per estrarre dati strutturati.
    """
    
    @staticmethod
    def extract_ilmeteo(soup: BeautifulSoup) -> Optional[str]:
        """
        Extractor specifico per ilmeteo.it
        """
        try:
            parts = []
            
            # Titolo pagina
            title = soup.find('h1')
            if title:
                parts.append(f"**{title.get_text(strip=True)}**")
            
            # Previsioni giornaliere
            forecasts = soup.find_all(class_=re.compile(r'(forecast|previsione|giorno)', re.I))
            for fc in forecasts[:5]:  # Max 5 giorni
                text = fc.get_text(strip=True)
                if len(text) > 20:
                    parts.append(text)
            
            # Temperature
            temps = soup.find_all(class_=re.compile(r'(temp|temperatura)', re.I))
            for t in temps[:10]:
                text = t.get_text(strip=True)
                if any(c.isdigit() for c in text):
                    parts.append(text)
            
            # Descrizioni meteo
            descriptions = soup.find_all(['p', 'div'], class_=re.compile(r'(desc|weather|meteo)', re.I))
            for desc in descriptions[:5]:
                text = desc.get_text(strip=True)
                if len(text) > 30:
                    parts.append(text)
            
            if parts:
                return "\n".join(parts)
        
        except Exception as e:
            log.warning(f"ilmeteo handler failed: {e}")
        
        return None
    
    @staticmethod
    def extract_3bmeteo(soup: BeautifulSoup) -> Optional[str]:
        """
        Extractor per 3bmeteo.com
        """
        try:
            parts = []
            
            # Container previsioni
            main = soup.find(class_=re.compile(r'(main|content|forecast)', re.I))
            if main:
                # Tutti i paragrafi e div con contenuto
                for elem in main.find_all(['p', 'div', 'span']):
                    text = elem.get_text(strip=True)
                    if len(text) > 25 and not text.startswith(('©', 'Cookie')):
                        parts.append(text)
            
            if parts:
                return "\n\n".join(parts[:15])
        
        except Exception as e:
            log.warning(f"3bmeteo handler failed: {e}")
        
        return None
    
    @staticmethod
    def extract_news_site(soup: BeautifulSoup) -> Optional[str]:
        """
        Extractor generico per siti news (repubblica.it, corriere.it, etc.)
        """
        try:
            parts = []
            
            # Articolo principale
            article = soup.find('article') or soup.find(class_=re.compile(r'(article|post|story)', re.I))
            if article:
                # Titolo
                title = article.find(['h1', 'h2'])
                if title:
                    parts.append(f"# {title.get_text(strip=True)}")
                
                # Sottotitolo/abstract
                subtitle = article.find(class_=re.compile(r'(subtitle|abstract|summary)', re.I))
                if subtitle:
                    parts.append(subtitle.get_text(strip=True))
                
                # Paragrafi
                paragraphs = article.find_all('p')
                for p in paragraphs[:10]:
                    text = p.get_text(strip=True)
                    if len(text) > 40:
                        parts.append(text)
            
            if parts:
                return "\n\n".join(parts)
        
        except Exception as e:
            log.warning(f"news handler failed: {e}")
        
        return None
    
    @staticmethod
    def get_handler(url: str):
        """
        Ritorna handler appropriato per il dominio
        """
        url_lower = url.lower()
        
        if 'ilmeteo.it' in url_lower:
            return SpecialtyExtractor.extract_ilmeteo
        elif '3bmeteo.com' in url_lower or 'meteoam.it' in url_lower:
            return SpecialtyExtractor.extract_3bmeteo
        elif any(site in url_lower for site in ['repubblica.it', 'corriere.it', 'ansa.it', 'lastampa.it']):
            return SpecialtyExtractor.extract_news_site
        
        return None


# ==================== MULTI-STRATEGY EXTRACTOR ====================

def extract_content_robust(html: str, url: str) -> str:
    """
    Extraction con 5 strategie in cascata + specialty handlers.
    GARANTISCE sempre un output utile.
    
    Strategie in ordine:
    1. Specialty handler per dominio specifico
    2. Trafilatura (best quality)
    3. Readability (good quality)
    4. Aggressive HTML parsing
    5. Metadata + first paragraphs (last resort)
    
    Args:
        html: HTML raw della pagina
        url: URL per domain detection
    
    Returns:
        Testo estratto (MAI stringa vuota)
    """
    
    if not html:
        return f"[Contenuto non disponibile per {url}]"
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove noise
    for element in soup(['script', 'style', 'noscript', 'iframe']):
        element.decompose()
    
    # Remove comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    
    # ===== STRATEGY 1: Specialty Handler =====
    handler = SpecialtyExtractor.get_handler(url)
    if handler:
        try:
            result = handler(soup)
            if result and len(result) > 100:
                log.info(f"✅ Specialty handler success for {url}")
                return result
        except Exception as e:
            log.warning(f"Specialty handler failed for {url}: {e}")
    
    # ===== STRATEGY 2: Trafilatura =====
    try:
        import trafilatura
        
        result = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        
        if result and len(result) > 200:
            log.info(f"✅ Trafilatura success for {url}")
            return result
    
    except Exception as e:
        log.debug(f"Trafilatura failed for {url}: {e}")
    
    # ===== STRATEGY 3: Readability =====
    try:
        from readability import Document
        
        doc = Document(html)
        title = doc.title()
        content = doc.summary()
        
        # Parse and clean
        content_soup = BeautifulSoup(content, 'html.parser')
        text = content_soup.get_text(separator='\n\n', strip=True)
        
        if title and text:
            result = f"# {title}\n\n{text}"
            if len(result) > 200:
                log.info(f"✅ Readability success for {url}")
                return result
    
    except Exception as e:
        log.debug(f"Readability failed for {url}: {e}")
    
    # ===== STRATEGY 4: Aggressive HTML Parsing =====
    result = _extract_aggressive_enhanced(soup)
    if result and len(result) > 150:
        log.info(f"✅ Aggressive parsing success for {url}")
        return result
    
    # ===== STRATEGY 5: Metadata + Paragraphs (Last Resort) =====
    result = _extract_metadata_and_content(soup)
    if result:
        log.info(f"⚠️ Metadata fallback for {url}")
        return result
    
    # ABSOLUTE LAST RESORT: Plain text di tutto
    text = soup.get_text(separator=' ', strip=True)
    text = re.sub(r'\s+', ' ', text)
    
    if len(text) > 100:
        log.warning(f"⚠️ Plain text fallback for {url}")
        return text[:2000]  # Primi 2000 chars
    
    # Truly nothing found
    return f"[Contenuto non disponibile o troppo breve per {url}]"


def _extract_aggressive_enhanced(soup: BeautifulSoup) -> str:
    """
    Parsing HTML aggressivo con focus su contenuto semantico.
    """
    parts = []
    
    # Title
    title = soup.find(['h1', 'h2'])
    if title:
        parts.append(f"# {title.get_text(strip=True)}")
    
    # Main content containers (prioritize)
    main_containers = soup.find_all(
        ['article', 'main', 'div'],
        class_=re.compile(r'(content|main|article|post|entry|body)', re.I)
    )
    
    if main_containers:
        for container in main_containers[:3]:
            # All meaningful text elements
            for elem in container.find_all(['p', 'div', 'li', 'span', 'h3', 'h4']):
                text = elem.get_text(strip=True)
                
                # Filter noise
                if (len(text) > 30 and 
                    not text.startswith(('©', 'Cookie', 'Privacy', 'Loading')) and
                    not re.match(r'^[\d\s\-\./]+$', text)):  # Not just numbers/dates
                    parts.append(text)
    
    else:
        # Fallback: all paragraphs
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            if len(text) > 40:
                parts.append(text)
    
    # Lists (for structured content)
    for ul in soup.find_all(['ul', 'ol'])[:5]:
        items = [li.get_text(strip=True) for li in ul.find_all('li')]
        if items:
            parts.append('\n'.join(f"• {item}" for item in items if len(item) > 10))
    
    return '\n\n'.join(parts[:30])  # Max 30 blocks


def _extract_metadata_and_content(soup: BeautifulSoup) -> str:
    """
    Last resort: metadata + primi paragrafi trovati.
    """
    parts = []
    
    # Title
    title_tag = soup.find('title')
    if title_tag:
        parts.append(f"# {title_tag.get_text(strip=True)}")
    
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        parts.append(meta_desc['content'])
    
    # OG description
    og_desc = soup.find('meta', attrs={'property': 'og:description'})
    if og_desc and og_desc.get('content'):
        parts.append(og_desc['content'])
    
    # First 10 paragraphs
    for p in soup.find_all('p')[:10]:
        text = p.get_text(strip=True)
        if len(text) > 50:
            parts.append(text)
    
    return '\n\n'.join(parts) if parts else ""


# ==================== INTEGRATION GUIDE ====================

def generate_web_tools_patch():
    """
    Patch per core/web_tools.py
    """
    
    return '''
# ============ SOSTITUISCI fetch_and_extract_robust ============
#
# In core/web_tools.py, trova fetch_and_extract_robust() e SOSTITUISCI con:

from robust_content_extraction import extract_content_robust

async def fetch_and_extract_robust(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_retries: int = 2,
) -> Tuple[str, Optional[str]]:
    """
    Fetch con multi-strategy extraction (NUOVO).
    """
    last_error = None
    
    async def _http_get_async(u: str, t: float) -> Optional[requests.Response]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _http_get, u, t)
    
    for attempt in range(max_retries):
        try:
            resp = await _http_get_async(url, timeout)
            if not resp:
                continue
            
            html = resp.content[:MAX_HTML_BYTES].decode("utf-8", errors="replace")
            og_image = _extract_og_image(html, resp.url)
            
            # NUOVO: usa extract_content_robust
            text = extract_content_robust(html, url)
            
            # Verifica minima qualità
            if text and len(text) > 100:
                return text, og_image
        
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
    
    # LAST RESORT
    return f"[Contenuto non disponibile per {url}. Errore: {last_error}]", None
'''


if __name__ == "__main__":
    print(generate_web_tools_patch())
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║            ROBUST CONTENT EXTRACTION DEPLOYMENT                       ║
╔══════════════════════════════════════════════════════════════════════╗

DEPENDENCIES CHECK:
--------------------
pip install beautifulsoup4 lxml trafilatura readability-lxml

STEP 1: Copy file
------------------
scp robust_content_extraction.py root@your-server:/root/quantumdev-open/core/

STEP 2: Backup web_tools.py
-----------------------------
cd /root/quantumdev-open
cp core/web_tools.py core/web_tools.py.backup-extraction

STEP 3: Edit core/web_tools.py
--------------------------------
1. Aggiungi import all'inizio:
   
   from robust_content_extraction import extract_content_robust

2. Trova fetch_and_extract_robust() (circa linea 150-250)

3. SOSTITUISCI il corpo con:
   
   ```python
   # ... (mantieni signature e async wrapper)
   
   # NUOVO: usa extract_content_robust invece delle strategy originali
   text = extract_content_robust(html, url)
   
   if text and len(text) > 100:
       return text, og_image
   ```

STEP 4: Restart
----------------
sudo systemctl restart quantum-api

STEP 5: Test critical cases
-----------------------------
# Meteo sites
curl -X POST "http://127.0.0.1:8081/web/search" \\
  -H "Content-Type: application/json" \\
  -d '{"q": "meteo Roma domani", "k": 5, "source": "test", "source_id": "test"}'

# News sites
curl -X POST "http://127.0.0.1:8081/web/search" \\
  -H "Content-Type: application/json" \\
  -d '{"q": "ultime notizie Italia", "k": 5, "source": "test", "source_id": "test"}'

# Technical docs
curl -X POST "http://127.0.0.1:8081/web/search" \\
  -H "Content-Type: application/json" \\
  -d '{"q": "python asyncio tutorial", "k": 5, "source": "test", "source_id": "test"}'

EXPECTED RESULTS:
------------------
✅ ilmeteo.it, 3bmeteo.com → temperature, condizioni estratte
✅ news sites → titolo + primi paragrafi + sommario
✅ technical docs → contenuto principale ben formattato
✅ Fallback graceful → sempre qualcosa di utile (mai empty)

LOG PATTERNS TO WATCH:
-----------------------
"✅ Specialty handler success" → dominio riconosciuto e gestito
"✅ Trafilatura success" → extraction di alta qualità
"⚠️ Metadata fallback" → extraction parziale ma utile
"⚠️ Plain text fallback" → ultimo resort

ROLLBACK (if needed):
----------------------
cd /root/quantumdev-open
mv core/web_tools.py core/web_tools.py.broken
mv core/web_tools.py.backup-extraction core/web_tools.py
sudo systemctl restart quantum-api

╚══════════════════════════════════════════════════════════════════════╝
""")
    
    # Test examples
    print("\n" + "="*80)
    print("EXAMPLE: Extract from ilmeteo.it HTML")
    print("="*80)
    
    # Simulate ilmeteo.it HTML
    sample_html = '''
    <html>
    <head><title>Meteo Roma - Previsioni</title></head>
    <body>
        <h1>Previsioni Meteo Roma</h1>
        <div class="forecast-day">
            <span class="temp-max">18°C</span>
            <span class="temp-min">12°C</span>
            <p class="desc-meteo">Cielo sereno con nubi sparse nel pomeriggio</p>
        </div>
        <div class="forecast-day">
            <span class="temp-max">19°C</span>
            <span class="temp-min">13°C</span>
            <p class="desc-meteo">Parzialmente nuvoloso, possibili rovesci serali</p>
        </div>
    </body>
    </html>
    '''
    
    result = extract_content_robust(sample_html, "https://www.ilmeteo.it/meteo/Roma")
    print(f"\nExtracted content:\n{result}\n")
    print("="*80)
