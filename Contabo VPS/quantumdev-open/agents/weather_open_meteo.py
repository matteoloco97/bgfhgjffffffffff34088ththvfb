#!/usr/bin/env python3
"""
agents/weather_open_meteo.py
============================

Agente meteo dedicato per Jarvis.
Usa Open-Meteo API (gratuita, no API key) per dati meteo strutturati.

Vantaggi rispetto a SERP + LLM:
- Dati numerici precisi (temperatura, precipitazioni, vento)
- Risposta strutturata e consistente
- Nessuna hallucination sui numeri
- Velocità: 1 API call invece di SERP + fetch + LLM
"""

import asyncio
import logging
import re
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ===================== GEOCODING =====================

# Cache semplice per geocoding (evita chiamate ripetute)
_GEO_CACHE: Dict[str, Tuple[float, float, str]] = {}

# Città italiane comuni con coordinate predefinite (fallback rapido)
_COMMON_CITIES: Dict[str, Tuple[float, float, str]] = {
    "roma": (41.9028, 12.4964, "Roma"),
    "milano": (45.4642, 9.1900, "Milano"),
    "napoli": (40.8518, 14.2681, "Napoli"),
    "torino": (45.0703, 7.6869, "Torino"),
    "palermo": (38.1157, 13.3615, "Palermo"),
    "genova": (44.4056, 8.9463, "Genova"),
    "bologna": (44.4949, 11.3426, "Bologna"),
    "firenze": (43.7696, 11.2558, "Firenze"),
    "bari": (41.1171, 16.8719, "Bari"),
    "catania": (37.5079, 15.0830, "Catania"),
    "venezia": (45.4408, 12.3155, "Venezia"),
    "verona": (45.4384, 10.9916, "Verona"),
    "messina": (38.1938, 15.5540, "Messina"),
    "padova": (45.4064, 11.8768, "Padova"),
    "trieste": (45.6495, 13.7768, "Trieste"),
    "brescia": (45.5416, 10.2118, "Brescia"),
    "parma": (44.8015, 10.3279, "Parma"),
    "modena": (44.6471, 10.9252, "Modena"),
    "reggio calabria": (38.1147, 15.6501, "Reggio Calabria"),
    "reggio emilia": (44.6989, 10.6297, "Reggio Emilia"),
    "perugia": (43.1107, 12.3908, "Perugia"),
    "livorno": (43.5485, 10.3106, "Livorno"),
    "ravenna": (44.4184, 12.2035, "Ravenna"),
    "cagliari": (39.2238, 9.1217, "Cagliari"),
    "foggia": (41.4621, 15.5444, "Foggia"),
    "rimini": (44.0678, 12.5695, "Rimini"),
    "salerno": (40.6824, 14.7681, "Salerno"),
    "ferrara": (44.8381, 11.6198, "Ferrara"),
    "sassari": (40.7259, 8.5556, "Sassari"),
    "siracusa": (37.0755, 15.2866, "Siracusa"),
    "pescara": (42.4618, 14.2161, "Pescara"),
    "monza": (45.5845, 9.2744, "Monza"),
    "bergamo": (45.6983, 9.6773, "Bergamo"),
    "trento": (46.0748, 11.1217, "Trento"),
    "vicenza": (45.5455, 11.5354, "Vicenza"),
    "terni": (42.5636, 12.6427, "Terni"),
    "novara": (45.4469, 8.6220, "Novara"),
    "piacenza": (45.0526, 9.6929, "Piacenza"),
    "ancona": (43.6158, 13.5189, "Ancona"),
    "arezzo": (43.4631, 11.8783, "Arezzo"),
    "udine": (46.0711, 13.2346, "Udine"),
    "lecce": (40.3516, 18.1718, "Lecce"),
    "pesaro": (43.9096, 12.9135, "Pesaro"),
    # Città europee comuni
    "londra": (51.5074, -0.1278, "Londra"),
    "london": (51.5074, -0.1278, "London"),
    "parigi": (48.8566, 2.3522, "Parigi"),
    "paris": (48.8566, 2.3522, "Paris"),
    "berlino": (52.5200, 13.4050, "Berlino"),
    "berlin": (52.5200, 13.4050, "Berlin"),
    "madrid": (40.4168, -3.7038, "Madrid"),
    "barcellona": (41.3851, 2.1734, "Barcellona"),
    "barcelona": (41.3851, 2.1734, "Barcelona"),
    "amsterdam": (52.3676, 4.9041, "Amsterdam"),
    "bruxelles": (50.8503, 4.3517, "Bruxelles"),
    "vienna": (48.2082, 16.3738, "Vienna"),
    "zurigo": (47.3769, 8.5417, "Zurigo"),
    "zurich": (47.3769, 8.5417, "Zurich"),
    "monaco": (48.1351, 11.5820, "Monaco di Baviera"),
    "new york": (40.7128, -74.0060, "New York"),
}


async def _geocode_city(city: str) -> Optional[Tuple[float, float, str]]:
    """
    Geocoding della città usando Open-Meteo Geocoding API.
    Ritorna (lat, lon, nome_formattato) o None se non trovata.
    """
    city_lower = city.lower().strip()
    
    # 1. Check cache
    if city_lower in _GEO_CACHE:
        return _GEO_CACHE[city_lower]
    
    # 2. Check città comuni predefinite
    if city_lower in _COMMON_CITIES:
        result = _COMMON_CITIES[city_lower]
        _GEO_CACHE[city_lower] = result
        return result
    
    # 3. Chiama API Open-Meteo Geocoding
    try:
        import aiohttp
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=it"
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    log.warning(f"Geocoding API returned {resp.status} for {city}")
                    return None
                
                data = await resp.json()
                results = data.get("results", [])
                
                if not results:
                    log.info(f"No geocoding results for: {city}")
                    return None
                
                first = results[0]
                lat = first.get("latitude")
                lon = first.get("longitude")
                name = first.get("name", city)
                country = first.get("country", "")
                
                formatted_name = f"{name}, {country}" if country else name
                result = (lat, lon, formatted_name)
                
                # Cache result
                _GEO_CACHE[city_lower] = result
                return result
                
    except Exception as e:
        log.error(f"Geocoding error for {city}: {e}")
        return None


# ===================== WEATHER API =====================

def _interpret_weather_code(code: int) -> str:
    """Interpreta il codice meteo WMO in descrizione italiana."""
    codes = {
        0: "Sereno ☀️",
        1: "Prevalentemente sereno 🌤️",
        2: "Parzialmente nuvoloso ⛅",
        3: "Nuvoloso ☁️",
        45: "Nebbia 🌫️",
        48: "Nebbia con brina 🌫️",
        51: "Pioggerella leggera 🌧️",
        53: "Pioggerella moderata 🌧️",
        55: "Pioggerella intensa 🌧️",
        56: "Pioggia gelata leggera 🌨️",
        57: "Pioggia gelata intensa 🌨️",
        61: "Pioggia leggera 🌧️",
        63: "Pioggia moderata 🌧️",
        65: "Pioggia intensa 🌧️",
        66: "Pioggia gelata leggera 🌨️",
        67: "Pioggia gelata intensa 🌨️",
        71: "Neve leggera ❄️",
        73: "Neve moderata ❄️",
        75: "Neve intensa ❄️",
        77: "Granelli di neve ❄️",
        80: "Rovesci leggeri 🌦️",
        81: "Rovesci moderati 🌦️",
        82: "Rovesci violenti ⛈️",
        85: "Rovesci di neve leggeri 🌨️",
        86: "Rovesci di neve intensi 🌨️",
        95: "Temporale ⛈️",
        96: "Temporale con grandine leggera ⛈️",
        99: "Temporale con grandine intensa ⛈️",
    }
    return codes.get(code, f"Codice {code}")


async def _fetch_weather(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Fetch previsioni meteo da Open-Meteo API.
    Ritorna dati strutturati per i prossimi 3 giorni.
    """
    try:
        import aiohttp
        
        # Parametri richiesti
        params = (
            f"latitude={lat}&longitude={lon}"
            "&hourly=temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
            "&timezone=Europe%2FRome"
            "&forecast_days=3"
        )
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    log.error(f"Weather API returned {resp.status}")
                    return None
                
                return await resp.json()
                
    except Exception as e:
        log.error(f"Weather fetch error: {e}")
        return None


def _format_weather_response(city_name: str, data: Dict[str, Any]) -> str:
    """
    Formatta i dati meteo in una risposta leggibile per Telegram.
    """
    daily = data.get("daily", {})
    
    dates = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    wind_max = daily.get("wind_speed_10m_max", [])
    weather_codes = daily.get("weather_code", [])
    
    if not dates:
        return f"Dati meteo non disponibili per {city_name}."
    
    # Formatta ogni giorno
    lines = [f"🌍 **Meteo {city_name}** – prossimi 3 giorni\n"]
    
    day_names = ["Oggi", "Domani", "Dopodomani"]
    
    for i, date in enumerate(dates[:3]):
        day_label = day_names[i] if i < len(day_names) else date
        
        t_max = max_temps[i] if i < len(max_temps) else "?"
        t_min = min_temps[i] if i < len(min_temps) else "?"
        rain = precip[i] if i < len(precip) else 0
        wind = wind_max[i] if i < len(wind_max) else "?"
        code = weather_codes[i] if i < len(weather_codes) else 0
        
        weather_desc = _interpret_weather_code(code)
        
        # Formatta linea
        line = f"• **{day_label}**: {t_min}–{t_max}°C, {weather_desc}"
        
        if rain and rain > 0.5:
            line += f", pioggia ~{rain:.1f}mm"
        
        if wind and wind > 15:
            line += f", vento max {wind:.0f} km/h"
        
        lines.append(line)
    
    lines.append(f"\n📡 Fonte: Open-Meteo (dati aggiornati)")
    
    return "\n".join(lines)


# ===================== INPUT CLEANING =====================

def clean_city_name(raw: str) -> str:
    """
    Pulisce il nome della città rimuovendo punteggiatura finale,
    spazi extra e normalizzando il formato.
    
    Es: "roma?" → "roma"
        "Milano!" → "milano"
        "  napoli  " → "napoli"
        "Roma, Italia" → "roma, italia"
    """
    if not raw:
        return ""
    
    # Strip spazi iniziali e finali
    name = raw.strip()
    
    # Rimuovi punteggiatura finale (?, !, ., ,, ;, :)
    while name and name[-1] in "?!.,;:":
        name = name[:-1]
    
    # Strip ancora dopo rimozione punteggiatura
    name = name.strip()
    
    # Normalizza a lowercase per matching
    return name.lower()


# ===================== PUBLIC API =====================

def extract_city_from_query(query: str) -> Optional[str]:
    """
    Estrae il nome della città da una query meteo.
    Es: "meteo roma" → "roma"
        "che tempo fa a milano" → "milano"
        "previsioni napoli domani" → "napoli"
        "meteo roma?" → "roma"  (gestisce punteggiatura)
    """
    # Prima pulisci l'input generale
    q = clean_city_name(query)
    
    # Pattern comuni
    patterns = [
        r"meteo\s+(?:a\s+)?(.+?)(?:\s+oggi|\s+domani|\s+settimana)?$",
        r"che\s+tempo\s+(?:fa\s+)?(?:a\s+)?(.+?)(?:\s+oggi|\s+domani)?$",
        r"previsioni\s+(?:meteo\s+)?(?:per\s+)?(?:a\s+)?(.+?)(?:\s+oggi|\s+domani)?$",
        r"tempo\s+(?:a\s+)?(.+?)(?:\s+oggi|\s+domani)?$",
        r"weather\s+(?:in\s+)?(.+?)$",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            city = match.group(1).strip()
            # Pulisci parole residue
            city = re.sub(r"\b(oggi|domani|dopodomani|settimana|prossimi|giorni)\b", "", city).strip()
            # Pulisci anche punteggiatura dalla città estratta
            city = clean_city_name(city)
            if city and len(city) > 1:
                return city
    
    # Fallback: prova a trovare una città conosciuta nel testo
    for city_key in _COMMON_CITIES:
        if city_key in q:
            return city_key
    
    return None


def is_weather_query(query: str) -> bool:
    """
    Determina se la query è una richiesta meteo.
    """
    # Pulisci l'input prima del check
    q = clean_city_name(query)
    weather_keywords = [
        "meteo", "che tempo", "previsioni", "weather",
        "temperatura", "pioggia", "neve", "nuvoloso",
        "sereno", "temporale", "grandine"
    ]
    return any(kw in q for kw in weather_keywords)


def _find_similar_cities(city: str) -> List[str]:
    """
    Trova città simili nel database per suggerimenti.
    Usa matching fuzzy semplice (prefisso/contenimento).
    """
    city_lower = city.lower().strip()
    suggestions = []
    
    for known_city in _COMMON_CITIES.keys():
        # Match per prefisso
        if known_city.startswith(city_lower[:3]) if len(city_lower) >= 3 else False:
            suggestions.append(_COMMON_CITIES[known_city][2])  # Nome formattato
        # Match per contenimento
        elif city_lower in known_city or known_city in city_lower:
            suggestions.append(_COMMON_CITIES[known_city][2])
    
    # Rimuovi duplicati e limita a 3 suggerimenti
    return list(dict.fromkeys(suggestions))[:3]


async def get_weather_answer(city: str) -> str:
    """
    API principale: dato il nome di una città, restituisce la risposta meteo formattata.
    
    Args:
        city: Nome della città (es. "Roma", "Milano", "Napoli")
    
    Returns:
        Stringa formattata con le previsioni meteo o messaggio di errore.
    """
    if not city:
        return "❌ Specifica una città. Es: `/web meteo Roma`"
    
    # Pulisci il nome della città prima del geocoding
    clean_city = clean_city_name(city)
    
    if not clean_city:
        return "❌ Specifica una città valida. Es: `meteo Roma`, `meteo Milano`"
    
    # 1. Geocoding
    geo_result = await _geocode_city(clean_city)
    
    if not geo_result:
        # Prova a trovare suggerimenti
        suggestions = _find_similar_cities(clean_city)
        if suggestions:
            sugg_text = ", ".join(suggestions)
            return f"❌ Città '{city}' non trovata. Forse intendevi: {sugg_text}?"
        else:
            return f"❌ Città '{city}' non trovata. Prova con un nome più specifico (es: 'Roma, Italia')."
    
    lat, lon, formatted_name = geo_result
    log.info(f"Weather request: {city} → {formatted_name} ({lat}, {lon})")
    
    # 2. Fetch meteo
    weather_data = await _fetch_weather(lat, lon)
    
    if not weather_data:
        return f"❌ Impossibile recuperare dati meteo per {formatted_name}. Riprova tra poco."
    
    # 3. Formatta risposta
    return _format_weather_response(formatted_name, weather_data)


async def get_weather_for_query(query: str) -> Optional[str]:
    """
    Wrapper: estrae la città dalla query e restituisce la risposta meteo.
    Ritorna None se non è una query meteo valida.
    """
    if not is_weather_query(query):
        return None
    
    city = extract_city_from_query(query)
    
    if not city:
        return "❌ Non ho capito quale città. Prova: `meteo Roma` o `che tempo fa a Milano`"
    
    return await get_weather_answer(city)
