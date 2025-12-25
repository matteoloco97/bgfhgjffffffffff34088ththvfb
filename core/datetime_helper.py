#!/usr/bin/env python3
# core/datetime_helper.py - Temporal Context Helper

from datetime import datetime, timedelta
import pytz
from typing import Dict

# Timezone per il bot
TIMEZONE = pytz.timezone('Europe/Rome')

def get_current_time() -> Dict[str, str]:
    """
    Ritorna informazioni temporali complete.
    
    Returns:
        Dict con datetime, date, time, weekday, timezone, human-readable
    """
    now = datetime.now(TIMEZONE)
    
    # Nomi giorni in italiano
    weekdays_it = {
        'Monday': 'Lunedì',
        'Tuesday': 'Martedì',
        'Wednesday': 'Mercoledì',
        'Thursday': 'Giovedì',
        'Friday': 'Venerdì',
        'Saturday': 'Sabato',
        'Sunday': 'Domenica'
    }
    
    # Mesi in italiano
    months_it = {
        1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile',
        5: 'Maggio', 6: 'Giugno', 7: 'Luglio', 8: 'Agosto',
        9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre'
    }
    
    weekday_en = now.strftime('%A')
    weekday_it = weekdays_it.get(weekday_en, weekday_en)
    month_it = months_it.get(now.month, str(now.month))
    
    return {
        'datetime': now.isoformat(),
        'date': now.strftime('%Y-%m-%d'),
        'time': now.strftime('%H:%M:%S'),
        'weekday': weekday_it,
        'weekday_en': weekday_en,
        'month': month_it,
        'year': str(now.year),
        'timezone': 'Europe/Rome',
        'timezone_abbr': 'CET/CEST',
        'human': f"{now.day} {month_it} {now.year}, {now.strftime('%H:%M')}",
        'human_full': f"{weekday_it} {now.day} {month_it} {now.year}, ore {now.strftime('%H:%M')}"
    }

def format_datetime_context() -> str:
    """
    Genera contesto temporale per system prompt LLM.
    
    Returns:
        Stringa formattata per context injection
    """
    info = get_current_time()
    
    context = (
        f"CONTESTO TEMPORALE:\n"
        f"Data e ora attuali: {info['human_full']}\n"
        f"Timezone: {info['timezone']} ({info['timezone_abbr']})\n"
        f"Anno: {info['year']}\n"
    )
    
    return context

def get_relative_time(days_offset: int = 0) -> Dict[str, str]:
    """
    Calcola data relativa (ieri, domani, etc).
    
    Args:
        days_offset: Giorni di offset (negativo = passato, positivo = futuro)
    
    Returns:
        Dict con informazioni sulla data relativa
    """
    now = datetime.now(TIMEZONE)
    target = now + timedelta(days=days_offset)
    
    # Labels comuni
    if days_offset == 0:
        label = "Oggi"
    elif days_offset == -1:
        label = "Ieri"
    elif days_offset == 1:
        label = "Domani"
    elif days_offset == -2:
        label = "L'altro ieri"
    elif days_offset == 2:
        label = "Dopodomani"
    elif days_offset < 0:
        label = f"{abs(days_offset)} giorni fa"
    else:
        label = f"Tra {days_offset} giorni"
    
    return {
        'date': target.strftime('%Y-%m-%d'),
        'human': target.strftime('%d/%m/%Y'),
        'label': label,
        'weekday': target.strftime('%A'),
        'days_offset': days_offset
    }

def is_business_hours() -> bool:
    """Verifica se siamo in orario lavorativo (9-18, lun-ven)"""
    now = datetime.now(TIMEZONE)
    
    # Weekend
    if now.weekday() >= 5:  # Sabato=5, Domenica=6
        return False
    
    # Orario
    if 9 <= now.hour < 18:
        return True
    
    return False

def format_timestamp(ts: datetime) -> str:
    """
    Formatta timestamp in formato user-friendly.
    
    Args:
        ts: datetime object (timezone-aware o naive)
    
    Returns:
        Stringa formattata
    """
    # Se naive, assume Europe/Rome
    if ts.tzinfo is None:
        ts = TIMEZONE.localize(ts)
    else:
        ts = ts.astimezone(TIMEZONE)
    
    now = datetime.now(TIMEZONE)
    diff = now - ts
    
    # Oggi
    if diff.days == 0:
        return f"Oggi alle {ts.strftime('%H:%M')}"
    
    # Ieri
    if diff.days == 1:
        return f"Ieri alle {ts.strftime('%H:%M')}"
    
    # Questa settimana
    if diff.days < 7:
        weekday_map = {
            0: 'Lunedì', 1: 'Martedì', 2: 'Mercoledì',
            3: 'Giovedì', 4: 'Venerdì', 5: 'Sabato', 6: 'Domenica'
        }
        return f"{weekday_map[ts.weekday()]} alle {ts.strftime('%H:%M')}"
    
    # Data completa
    return ts.strftime('%d/%m/%Y alle %H:%M')


# === TESTS ===
if __name__ == "__main__":
    print("⏰ DATETIME HELPER - TEST\n")
    print("=" * 60)
    
    # Test 1: Current time
    print("📅 Current Time Info:")
    info = get_current_time()
    for key, value in info.items():
        print(f"  {key:15} : {value}")
    
    print("\n" + "=" * 60)
    
    # Test 2: Context for LLM
    print("🤖 LLM Context:\n")
    print(format_datetime_context())
    
    print("=" * 60)
    
    # Test 3: Relative times
    print("📆 Relative Times:\n")
    for offset in [-2, -1, 0, 1, 2, 7]:
        rel = get_relative_time(offset)
        print(f"  {rel['label']:15} → {rel['human']} ({rel['weekday']})")
    
    print("\n" + "=" * 60)
    
    # Test 4: Business hours
    print("💼 Business Hours Check:")
    if is_business_hours():
        print("  ✅ Orario lavorativo (9-18, Lun-Ven)")
    else:
        print("  ❌ Fuori orario lavorativo")
    
    print("\n" + "=" * 60)
    
    # Test 5: Timestamp formatting
    print("🕐 Timestamp Formatting:\n")
    
    now = datetime.now(TIMEZONE)
    test_times = [
        (now, "Adesso"),
        (now - timedelta(hours=2), "2 ore fa"),
        (now - timedelta(days=1), "Ieri"),
        (now - timedelta(days=3), "3 giorni fa"),
    ]
    
    for ts, label in test_times:
        formatted = format_timestamp(ts)
        print(f"  {label:15} → {formatted}")
    
    print("\n" + "=" * 60)
    print("✅ DATETIME HELPER - READY\n")
