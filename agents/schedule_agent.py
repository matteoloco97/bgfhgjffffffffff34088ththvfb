#!/usr/bin/env python3
"""
agents/schedule_agent.py
========================

Agente calendario/orari dedicato per Jarvis.
Gestisce query su orari eventi, partite, calendari.

Copre:
- Orari partite di calcio
- Calendario F1/MotoGP
- Eventi finanziari (FED, BCE, earning calls)
- Eventi generali

API usate:
- TheSportsDB (sport)
- Ergast API (F1)
- Fallback a dati statici per eventi macro

Formato risposta standardizzato:
- Emoji + titolo
- Blocco eventi verificati (✅)
- Blocco note (⚠️)
- Fonte con timestamp
"""

import asyncio
import logging
import re
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ===================== CONFIG =====================

SCHEDULE_API_TIMEOUT = float(os.getenv("SCHEDULE_API_TIMEOUT", "10.0"))

# ===================== TEAM/EVENT MAPPING =====================

# Usa stessi mapping di sports_agent
TEAMS_SIMPLE: Dict[str, str] = {
    "milan": "AC Milan",
    "inter": "Inter Milano",
    "juventus": "Juventus FC",
    "juve": "Juventus FC",
    "napoli": "SSC Napoli",
    "roma": "AS Roma",
    "lazio": "SS Lazio",
    "atalanta": "Atalanta BC",
    "fiorentina": "ACF Fiorentina",
    "real madrid": "Real Madrid CF",
    "barcellona": "FC Barcelona",
    "barcelona": "FC Barcelona",
    "manchester united": "Manchester United",
    "manchester city": "Manchester City",
    "liverpool": "Liverpool FC",
    "chelsea": "Chelsea FC",
    "arsenal": "Arsenal FC",
    "bayern": "FC Bayern München",
    "psg": "Paris Saint-Germain",
}

# Eventi finanziari ricorrenti (dati semi-statici, aggiornare periodicamente)
FINANCIAL_EVENTS: List[Dict[str, Any]] = [
    {
        "name": "FOMC Meeting (FED)",
        "type": "macro",
        "description": "Decisione tassi di interesse USA",
        "frequency": "ogni 6 settimane circa",
        "importance": "alta",
    },
    {
        "name": "BCE Meeting",
        "type": "macro",
        "description": "Decisione tassi di interesse Eurozona",
        "frequency": "ogni 6 settimane circa",
        "importance": "alta",
    },
    {
        "name": "Non-Farm Payrolls (NFP)",
        "type": "macro",
        "description": "Dati occupazione USA",
        "frequency": "primo venerdì del mese",
        "importance": "alta",
    },
    {
        "name": "CPI USA (Inflazione)",
        "type": "macro",
        "description": "Dati inflazione USA",
        "frequency": "mensile",
        "importance": "alta",
    },
    {
        "name": "CPI Europa (Inflazione)",
        "type": "macro",
        "description": "Dati inflazione Eurozona",
        "frequency": "mensile",
        "importance": "media",
    },
]

# ===================== API CALLS =====================


async def _fetch_team_schedule(team_name: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch prossime partite di una squadra da TheSportsDB.
    """
    try:
        import aiohttp

        # Cerca team
        url = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php"
        params = {"t": team_name}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=SCHEDULE_API_TIMEOUT)
        ) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                teams = data.get("teams")
                if not teams:
                    return None
                team_id = teams[0].get("idTeam")

            # Prossime partite
            next_url = "https://www.thesportsdb.com/api/v1/json/3/eventsnext.php"
            async with session.get(next_url, params={"id": team_id}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                events = data.get("events") or []

                schedule = []
                for event in events[:10]:
                    schedule.append(
                        {
                            "type": "football",
                            "home": event.get("strHomeTeam"),
                            "away": event.get("strAwayTeam"),
                            "date": event.get("dateEvent"),
                            "time": event.get("strTime", "TBD"),
                            "venue": event.get("strVenue", ""),
                            "league": event.get("strLeague"),
                        }
                    )

                return schedule

    except Exception as e:
        log.error(f"TheSportsDB schedule error: {e}")
        return None


async def _fetch_f1_schedule() -> Optional[List[Dict[str, Any]]]:
    """
    Fetch calendario F1 da Ergast API.
    """
    try:
        import aiohttp

        year = datetime.now().year
        url = f"https://ergast.com/api/f1/{year}.json"

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=SCHEDULE_API_TIMEOUT)
        ) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])

                schedule = []
                now = datetime.now()

                for race in races:
                    race_date_str = race.get("date", "")
                    race_time_str = race.get("time", "")

                    try:
                        if race_time_str:
                            race_dt = datetime.strptime(
                                f"{race_date_str} {race_time_str[:5]}",
                                "%Y-%m-%d %H:%M"
                            )
                        else:
                            race_dt = datetime.strptime(race_date_str, "%Y-%m-%d")
                    except ValueError:
                        race_dt = None

                    # Solo gare future
                    if race_dt and race_dt > now:
                        schedule.append(
                            {
                                "type": "f1",
                                "name": race.get("raceName"),
                                "circuit": race.get("Circuit", {}).get("circuitName"),
                                "location": race.get("Circuit", {}).get("Location", {}).get("country"),
                                "date": race_date_str,
                                "time": race_time_str[:5] if race_time_str else "TBD",
                                "round": race.get("round"),
                            }
                        )

                return schedule[:5]  # Solo le prossime 5

    except Exception as e:
        log.error(f"F1 schedule error: {e}")
        return None


async def _fetch_motogp_schedule() -> Optional[List[Dict[str, Any]]]:
    """
    Placeholder per calendario MotoGP.
    In futuro può essere collegato a API MotoGP.
    """
    # Per ora ritorna dati placeholder
    return [
        {
            "type": "motogp",
            "name": "Calendario MotoGP",
            "note": "Dati non disponibili in tempo reale. Consulta motogp.com per il calendario aggiornato.",
        }
    ]


def _get_financial_calendar() -> List[Dict[str, Any]]:
    """
    Ritorna calendario eventi finanziari (semi-statico).
    """
    return FINANCIAL_EVENTS


# ===================== FORMATTERS =====================


def _format_football_schedule(team_name: str, schedule: List[Dict[str, Any]]) -> str:
    """
    Formatta calendario partite in stile Jarvis.
    """
    lines = [f"📅 **Calendario {team_name}**\n"]

    lines.append("**✅ Prossime partite:**\n")

    for match in schedule[:5]:
        home = match.get("home", "?")
        away = match.get("away", "?")
        date = match.get("date", "TBD")
        time = match.get("time", "TBD")
        league = match.get("league", "")
        venue = match.get("venue", "")

        lines.append(f"• **{home}** vs **{away}**")
        lines.append(f"  📆 {date} ore {time}")
        if venue:
            lines.append(f"  🏟️ {venue}")
        lines.append(f"  🏆 {league}\n")

    lines.append("**⚠️ Nota:**")
    lines.append("• Gli orari potrebbero variare. Verifica sempre prima della partita.")

    lines.append(f"\n📡 Fonte: TheSportsDB (aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M')})")

    return "\n".join(lines)


def _format_f1_schedule(schedule: List[Dict[str, Any]]) -> str:
    """
    Formatta calendario F1 in stile Jarvis.
    """
    lines = ["🏎️ **Calendario F1 - Prossime gare**\n"]

    lines.append("**✅ Gran Premi in programma:**\n")

    for race in schedule:
        name = race.get("name", "GP")
        circuit = race.get("circuit", "")
        location = race.get("location", "")
        date = race.get("date", "TBD")
        time = race.get("time", "TBD")
        round_num = race.get("round", "")

        lines.append(f"**Round {round_num}: {name}**")
        lines.append(f"  📆 {date} ore {time} UTC")
        lines.append(f"  🏁 {circuit}")
        lines.append(f"  📍 {location}\n")

    lines.append("**⚠️ Nota:**")
    lines.append("• Orari in UTC. Aggiungi +1h (CET) o +2h (CEST) per l'ora italiana.")

    lines.append(f"\n📡 Fonte: Ergast F1 API (aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M')})")

    return "\n".join(lines)


def _format_financial_calendar(events: List[Dict[str, Any]]) -> str:
    """
    Formatta calendario eventi finanziari in stile Jarvis.
    """
    lines = ["💹 **Calendario Eventi Macro/Finanziari**\n"]

    lines.append("**✅ Eventi importanti da monitorare:**\n")

    for event in events:
        name = event.get("name", "")
        description = event.get("description", "")
        frequency = event.get("frequency", "")
        importance = event.get("importance", "media")

        emoji = "🔴" if importance == "alta" else "🟡"
        lines.append(f"{emoji} **{name}**")
        lines.append(f"   {description}")
        lines.append(f"   📆 {frequency}\n")

    lines.append("**⚠️ Nota:**")
    lines.append("• Per date esatte, consulta investing.com/economic-calendar")
    lines.append("• Gli eventi macro possono causare alta volatilità sui mercati")

    lines.append(f"\n📡 Fonte: Dati semi-statici (aggiornato: {datetime.now().strftime('%Y-%m-%d')})")

    return "\n".join(lines)


# ===================== QUERY EXTRACTION =====================


def extract_schedule_query(query: str) -> Optional[Dict[str, Any]]:
    """
    Estrae tipo di richiesta schedule dalla query.
    """
    q = query.lower().strip()

    # Check F1
    if any(kw in q for kw in ["f1", "formula 1", "formula1", "gran premio", "gp"]):
        return {"type": "f1"}

    # Check MotoGP
    if any(kw in q for kw in ["motogp", "moto gp", "moto"]):
        return {"type": "motogp"}

    # Check eventi finanziari
    if any(kw in q for kw in [
        "fed", "fomc", "bce", "ecb", "nfp", "non-farm", "inflazione", "cpi",
        "calendario macro", "eventi economici", "calendario economico",
        "riunione fed", "riunione bce"
    ]):
        return {"type": "financial"}

    # Check squadra calcio
    for alias, full_name in TEAMS_SIMPLE.items():
        if alias in q:
            return {
                "type": "football",
                "team": full_name,
                "team_alias": alias,
            }

    # Check generico "quando gioca"
    match = re.search(r"quando\s+gioca\s+(?:la\s+|il\s+)?(\w+)", q)
    if match:
        team_guess = match.group(1)
        full_name = TEAMS_SIMPLE.get(team_guess, team_guess.capitalize())
        return {
            "type": "football",
            "team": full_name,
            "team_alias": team_guess,
        }

    return None


def is_schedule_query(query: str) -> bool:
    """
    Determina se la query è una richiesta di calendario/orari.
    """
    q = query.lower().strip()

    schedule_keywords = [
        "quando gioca",
        "a che ora",
        "orario",
        "orari",
        "calendario",
        "schedule",
        "prossima partita",
        "prossimo gp",
        "prossima gara",
        "prossimo evento",
        "quando è",
        "quando sarà",
    ]

    # Check keywords espliciti
    if any(kw in q for kw in schedule_keywords):
        return True

    # Check F1/MotoGP
    if any(kw in q for kw in ["f1", "formula 1", "motogp", "gran premio"]):
        return True

    # Check eventi finanziari
    if any(kw in q for kw in ["fed", "fomc", "bce", "nfp", "calendario macro"]):
        return True

    return False


# ===================== PUBLIC API =====================


async def get_schedule_answer(query: str) -> Optional[str]:
    """
    API principale: data una query schedule, restituisce la risposta formattata.
    """
    parsed = extract_schedule_query(query)

    if not parsed:
        return "❌ Non ho capito la richiesta. Prova con: `quando gioca la Juve`, `calendario F1`, `prossima riunione FED`"

    query_type = parsed.get("type")

    try:
        if query_type == "football":
            team_name = parsed.get("team")
            schedule = await _fetch_team_schedule(team_name)
            if schedule:
                return _format_football_schedule(team_name, schedule)
            else:
                return f"❌ Impossibile recuperare il calendario per {team_name}. Riprova tra poco."

        elif query_type == "f1":
            schedule = await _fetch_f1_schedule()
            if schedule:
                return _format_f1_schedule(schedule)
            else:
                return "❌ Impossibile recuperare il calendario F1. Riprova tra poco."

        elif query_type == "motogp":
            return "⚠️ Calendario MotoGP non disponibile via API. Consulta motogp.com per le date aggiornate."

        elif query_type == "financial":
            events = _get_financial_calendar()
            return _format_financial_calendar(events)

    except Exception as e:
        log.error(f"Schedule agent error: {e}")
        return f"❌ Errore nel recupero calendario: {e}"

    return None


async def get_schedule_for_query(query: str) -> Optional[str]:
    """
    Wrapper: verifica se è una schedule query e restituisce la risposta.
    """
    if not is_schedule_query(query):
        return None

    return await get_schedule_answer(query)
