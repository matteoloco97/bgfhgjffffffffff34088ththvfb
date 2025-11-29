#!/usr/bin/env python3
"""
agents/sports_agent.py
======================

Agente sportivo dedicato per Jarvis.
Gestisce query su risultati, classifiche, orari partite.

API usate:
- API-Football (football-data.org) - free tier
- TheSportsDB - free API
- Scraping fallback per dati live

Formato risposta standardizzato:
- Emoji + titolo competizione
- Blocco dati verificati (✅)
- Blocco analisi/commenti (⚠️)
- Fonte con timestamp
"""

import asyncio
import logging
import re
import os
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ===================== CONFIG =====================

FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY", "")
SPORTS_API_TIMEOUT = float(os.getenv("SPORTS_API_TIMEOUT", "10.0"))

# ===================== TEAM/LEAGUE MAPPING =====================

# Mapping squadre italiane → ID (per API)
ITALIAN_TEAMS: Dict[str, Dict[str, Any]] = {
    # Serie A
    "milan": {"id": 489, "name": "AC Milan", "league": "Serie A"},
    "ac milan": {"id": 489, "name": "AC Milan", "league": "Serie A"},
    "inter": {"id": 108, "name": "Inter Milano", "league": "Serie A"},
    "inter milano": {"id": 108, "name": "Inter Milano", "league": "Serie A"},
    "internazionale": {"id": 108, "name": "Inter Milano", "league": "Serie A"},
    "juventus": {"id": 496, "name": "Juventus FC", "league": "Serie A"},
    "juve": {"id": 496, "name": "Juventus FC", "league": "Serie A"},
    "napoli": {"id": 492, "name": "SSC Napoli", "league": "Serie A"},
    "roma": {"id": 497, "name": "AS Roma", "league": "Serie A"},
    "as roma": {"id": 497, "name": "AS Roma", "league": "Serie A"},
    "lazio": {"id": 487, "name": "SS Lazio", "league": "Serie A"},
    "atalanta": {"id": 499, "name": "Atalanta BC", "league": "Serie A"},
    "fiorentina": {"id": 488, "name": "ACF Fiorentina", "league": "Serie A"},
    "torino": {"id": 503, "name": "Torino FC", "league": "Serie A"},
    "bologna": {"id": 500, "name": "Bologna FC", "league": "Serie A"},
    "udinese": {"id": 494, "name": "Udinese Calcio", "league": "Serie A"},
    "sassuolo": {"id": 471, "name": "US Sassuolo", "league": "Serie A"},
    "verona": {"id": 450, "name": "Hellas Verona", "league": "Serie A"},
    "hellas verona": {"id": 450, "name": "Hellas Verona", "league": "Serie A"},
    "empoli": {"id": 491, "name": "Empoli FC", "league": "Serie A"},
    "sampdoria": {"id": 488, "name": "UC Sampdoria", "league": "Serie A"},
    "genoa": {"id": 107, "name": "Genoa CFC", "league": "Serie A"},
    "monza": {"id": 5890, "name": "AC Monza", "league": "Serie A"},
    "lecce": {"id": 5879, "name": "US Lecce", "league": "Serie A"},
    "cagliari": {"id": 104, "name": "Cagliari Calcio", "league": "Serie A"},
    "parma": {"id": 112, "name": "Parma Calcio", "league": "Serie A"},
    "como": {"id": 1106, "name": "Como 1907", "league": "Serie A"},
    "venezia": {"id": 454, "name": "Venezia FC", "league": "Serie A"},
}

# Squadre internazionali popolari
INTERNATIONAL_TEAMS: Dict[str, Dict[str, Any]] = {
    "real madrid": {"id": 86, "name": "Real Madrid CF", "league": "La Liga"},
    "barcellona": {"id": 83, "name": "FC Barcelona", "league": "La Liga"},
    "barcelona": {"id": 83, "name": "FC Barcelona", "league": "La Liga"},
    "barca": {"id": 83, "name": "FC Barcelona", "league": "La Liga"},
    "barça": {"id": 83, "name": "FC Barcelona", "league": "La Liga"},
    "atletico madrid": {"id": 78, "name": "Atlético Madrid", "league": "La Liga"},
    "manchester united": {"id": 33, "name": "Manchester United", "league": "Premier League"},
    "man utd": {"id": 33, "name": "Manchester United", "league": "Premier League"},
    "manchester city": {"id": 65, "name": "Manchester City", "league": "Premier League"},
    "man city": {"id": 65, "name": "Manchester City", "league": "Premier League"},
    "liverpool": {"id": 64, "name": "Liverpool FC", "league": "Premier League"},
    "chelsea": {"id": 61, "name": "Chelsea FC", "league": "Premier League"},
    "arsenal": {"id": 57, "name": "Arsenal FC", "league": "Premier League"},
    "tottenham": {"id": 73, "name": "Tottenham Hotspur", "league": "Premier League"},
    "bayern": {"id": 5, "name": "FC Bayern München", "league": "Bundesliga"},
    "bayern monaco": {"id": 5, "name": "FC Bayern München", "league": "Bundesliga"},
    "bayern munich": {"id": 5, "name": "FC Bayern München", "league": "Bundesliga"},
    "borussia dortmund": {"id": 4, "name": "Borussia Dortmund", "league": "Bundesliga"},
    "dortmund": {"id": 4, "name": "Borussia Dortmund", "league": "Bundesliga"},
    "psg": {"id": 524, "name": "Paris Saint-Germain", "league": "Ligue 1"},
    "paris saint germain": {"id": 524, "name": "Paris Saint-Germain", "league": "Ligue 1"},
}

# Merge teams
ALL_TEAMS = {**ITALIAN_TEAMS, **INTERNATIONAL_TEAMS}

# Competizioni
COMPETITIONS: Dict[str, Dict[str, Any]] = {
    "serie a": {"id": "SA", "name": "Serie A", "country": "Italy"},
    "premier league": {"id": "PL", "name": "Premier League", "country": "England"},
    "la liga": {"id": "PD", "name": "La Liga", "country": "Spain"},
    "bundesliga": {"id": "BL1", "name": "Bundesliga", "country": "Germany"},
    "ligue 1": {"id": "FL1", "name": "Ligue 1", "country": "France"},
    "champions league": {"id": "CL", "name": "UEFA Champions League", "country": "Europe"},
    "champions": {"id": "CL", "name": "UEFA Champions League", "country": "Europe"},
    "europa league": {"id": "EL", "name": "UEFA Europa League", "country": "Europe"},
}

# ===================== API CALLS =====================


async def _fetch_team_matches(
    team_name: str, date_from: str = None, date_to: str = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch partite di una squadra da TheSportsDB (free API).
    """
    try:
        import aiohttp

        # TheSportsDB endpoint (free)
        url = f"https://www.thesportsdb.com/api/v1/json/3/searchteams.php"
        params = {"t": team_name}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=SPORTS_API_TIMEOUT)
        ) as session:
            # Prima cerca il team
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                teams = data.get("teams")
                if not teams:
                    return None

                team_id = teams[0].get("idTeam")
                team_full_name = teams[0].get("strTeam")

            # Poi cerca le ultime partite
            events_url = f"https://www.thesportsdb.com/api/v1/json/3/eventslast.php"
            async with session.get(events_url, params={"id": team_id}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                results = data.get("results") or []

                matches = []
                for event in results[:5]:
                    matches.append(
                        {
                            "home": event.get("strHomeTeam"),
                            "away": event.get("strAwayTeam"),
                            "home_score": event.get("intHomeScore"),
                            "away_score": event.get("intAwayScore"),
                            "date": event.get("dateEvent"),
                            "league": event.get("strLeague"),
                            "status": "finished",
                        }
                    )

                return matches

    except Exception as e:
        log.error(f"TheSportsDB API error: {e}")
        return None


async def _fetch_next_matches(team_name: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch prossime partite di una squadra.
    """
    try:
        import aiohttp

        url = f"https://www.thesportsdb.com/api/v1/json/3/searchteams.php"
        params = {"t": team_name}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=SPORTS_API_TIMEOUT)
        ) as session:
            # Cerca il team
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                teams = data.get("teams")
                if not teams:
                    return None
                team_id = teams[0].get("idTeam")

            # Prossime partite
            next_url = f"https://www.thesportsdb.com/api/v1/json/3/eventsnext.php"
            async with session.get(next_url, params={"id": team_id}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                events = data.get("events") or []

                matches = []
                for event in events[:5]:
                    matches.append(
                        {
                            "home": event.get("strHomeTeam"),
                            "away": event.get("strAwayTeam"),
                            "date": event.get("dateEvent"),
                            "time": event.get("strTime", "TBD"),
                            "league": event.get("strLeague"),
                            "status": "scheduled",
                        }
                    )

                return matches

    except Exception as e:
        log.error(f"TheSportsDB next matches error: {e}")
        return None


async def _fetch_league_standings(league_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch classifica di un campionato.
    Usa football-data.org se disponibile API key, altrimenti fallback.
    """
    try:
        import aiohttp

        if FOOTBALL_DATA_API_KEY:
            url = f"https://api.football-data.org/v4/competitions/{league_id}/standings"
            headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=SPORTS_API_TIMEOUT)
            ) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        log.warning(f"football-data.org returned {resp.status}")
                        return None

                    data = await resp.json()
                    standings = data.get("standings", [])
                    if not standings:
                        return None

                    table = standings[0].get("table", [])
                    result = []
                    for team in table[:20]:
                        result.append(
                            {
                                "position": team.get("position"),
                                "team": team.get("team", {}).get("name"),
                                "played": team.get("playedGames"),
                                "won": team.get("won"),
                                "draw": team.get("draw"),
                                "lost": team.get("lost"),
                                "points": team.get("points"),
                                "gf": team.get("goalsFor"),
                                "ga": team.get("goalsAgainst"),
                                "gd": team.get("goalDifference"),
                            }
                        )
                    return result

        # Fallback senza API key - dati simulati
        return None

    except Exception as e:
        log.error(f"Football standings API error: {e}")
        return None


# ===================== FORMATTERS =====================


def _format_match_result(match: Dict[str, Any]) -> str:
    """Formatta singolo risultato partita."""
    home = match.get("home", "?")
    away = match.get("away", "?")
    home_score = match.get("home_score", "?")
    away_score = match.get("away_score", "?")
    date = match.get("date", "")
    league = match.get("league", "")

    if home_score and away_score:
        return f"• {home} **{home_score}**–**{away_score}** {away} ({date}, {league})"
    else:
        return f"• {home} vs {away} ({date}, {league})"


def _format_next_match(match: Dict[str, Any]) -> str:
    """Formatta prossima partita."""
    home = match.get("home", "?")
    away = match.get("away", "?")
    date = match.get("date", "")
    time = match.get("time", "TBD")
    league = match.get("league", "")

    return f"• {home} vs {away} – {date} ore {time} ({league})"


def _format_team_results(team_name: str, matches: List[Dict[str, Any]]) -> str:
    """
    Formatta risultati di una squadra in stile Jarvis.
    """
    lines = [f"⚽ **Ultimi risultati {team_name}**\n"]

    lines.append("**✅ Partite giocate:**")
    for match in matches:
        lines.append(_format_match_result(match))

    # Calcola forma
    wins = sum(
        1
        for m in matches
        if m.get("status") == "finished"
        and _is_win(team_name, m)
    )
    draws = sum(
        1
        for m in matches
        if m.get("status") == "finished"
        and _is_draw(m)
    )
    losses = len(matches) - wins - draws

    lines.append(f"\n**⚠️ Forma recente:** {wins}V {draws}P {losses}S")

    if wins >= 3:
        lines.append("• Ottimo momento di forma 🔥")
    elif losses >= 3:
        lines.append("• Momento difficile ⚠️")

    lines.append(f"\n📡 Fonte: TheSportsDB (aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M')})")

    return "\n".join(lines)


def _format_next_matches(team_name: str, matches: List[Dict[str, Any]]) -> str:
    """
    Formatta prossime partite in stile Jarvis.
    """
    lines = [f"📅 **Prossime partite {team_name}**\n"]

    lines.append("**✅ Calendario:**")
    for match in matches:
        lines.append(_format_next_match(match))

    lines.append(f"\n📡 Fonte: TheSportsDB (aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M')})")

    return "\n".join(lines)


def _format_standings(league_name: str, standings: List[Dict[str, Any]]) -> str:
    """
    Formatta classifica in stile Jarvis.
    """
    lines = [f"🏆 **Classifica {league_name}**\n"]

    lines.append("**✅ Posizioni attuali:**")

    # Header compatto
    lines.append("```")
    lines.append(f"{'#':>2} {'Squadra':<20} {'PG':>3} {'V':>2} {'P':>2} {'S':>2} {'Pt':>3}")
    lines.append("-" * 42)

    for team in standings[:10]:  # Top 10
        pos = team.get("position", "?")
        name = (team.get("team") or "?")[:18]
        played = team.get("played", 0)
        won = team.get("won", 0)
        draw = team.get("draw", 0)
        lost = team.get("lost", 0)
        points = team.get("points", 0)

        lines.append(f"{pos:>2} {name:<20} {played:>3} {won:>2} {draw:>2} {lost:>2} {points:>3}")

    lines.append("```")

    lines.append("\n**⚠️ Legenda:** PG=Partite Giocate, V=Vittorie, P=Pareggi, S=Sconfitte, Pt=Punti")

    lines.append(f"\n📡 Fonte: football-data.org (aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M')})")

    return "\n".join(lines)


def _is_win(team_name: str, match: Dict[str, Any]) -> bool:
    """Verifica se la squadra ha vinto."""
    home = (match.get("home") or "").lower()
    away = (match.get("away") or "").lower()
    home_score = int(match.get("home_score") or 0)
    away_score = int(match.get("away_score") or 0)

    team_lower = team_name.lower()

    if team_lower in home:
        return home_score > away_score
    elif team_lower in away:
        return away_score > home_score
    return False


def _is_draw(match: Dict[str, Any]) -> bool:
    """Verifica se è pareggio."""
    home_score = int(match.get("home_score") or 0)
    away_score = int(match.get("away_score") or 0)
    return home_score == away_score


# ===================== QUERY EXTRACTION =====================


def extract_sports_query(query: str) -> Optional[Dict[str, Any]]:
    """
    Estrae tipo di richiesta sportiva dalla query.
    Ritorna dict con 'query_type' e parametri.
    """
    q = query.lower().strip()

    # Cerca squadra nella query
    team_found = None
    team_info = None

    for alias, info in ALL_TEAMS.items():
        if alias in q:
            team_found = alias
            team_info = info
            break

    # Cerca competizione
    league_found = None
    league_info = None

    for alias, info in COMPETITIONS.items():
        if alias in q:
            league_found = alias
            league_info = info
            break

    # Determina tipo query
    if any(kw in q for kw in ["risultato", "risultati", "score", "com'è finita", "quanto è finita", "chi ha vinto"]):
        if team_found:
            return {
                "type": "team_results",
                "team": team_info.get("name"),
                "team_alias": team_found,
            }
        elif league_found:
            return {
                "type": "league_results",
                "league": league_info.get("name"),
                "league_id": league_info.get("id"),
            }

    elif any(kw in q for kw in ["classifica", "standings", "table", "posizione"]):
        if league_found:
            return {
                "type": "standings",
                "league": league_info.get("name"),
                "league_id": league_info.get("id"),
            }
        elif team_found:
            # Inferisci campionato dalla squadra
            team_league = team_info.get("league", "Serie A")
            league_id = None
            for lname, linfo in COMPETITIONS.items():
                if linfo.get("name") == team_league:
                    league_id = linfo.get("id")
                    break
            return {
                "type": "standings",
                "league": team_league,
                "league_id": league_id,
            }

    elif any(kw in q for kw in ["quando gioca", "prossima partita", "prossime partite", "a che ora", "orario"]):
        if team_found:
            return {
                "type": "next_matches",
                "team": team_info.get("name"),
                "team_alias": team_found,
            }

    # Default: se c'è una squadra, mostra risultati recenti
    if team_found:
        return {
            "type": "team_results",
            "team": team_info.get("name"),
            "team_alias": team_found,
        }

    return None


def is_sports_query(query: str) -> bool:
    """
    Determina se la query è una richiesta sportiva.
    """
    q = query.lower().strip()

    sports_keywords = [
        "risultato", "risultati", "score", "partita", "partite",
        "chi ha vinto", "classifica", "standings", "quando gioca",
        "serie a", "premier league", "champions", "calcio",
        "gol", "marcatori", "formazione",
    ]

    # Check keywords
    has_sports_keyword = any(kw in q for kw in sports_keywords)

    # Check se contiene una squadra nota
    has_team = any(alias in q for alias in ALL_TEAMS)

    # Check se contiene una competizione nota
    has_league = any(alias in q for alias in COMPETITIONS)

    return has_sports_keyword or has_team or has_league


# ===================== PUBLIC API =====================


async def get_sports_answer(query: str) -> Optional[str]:
    """
    API principale: data una query sportiva, restituisce la risposta formattata.
    """
    parsed = extract_sports_query(query)

    if not parsed:
        return "❌ Non ho capito la richiesta sportiva. Prova con: `risultato Milan`, `classifica Serie A`, `quando gioca la Juve`"

    query_type = parsed.get("type")

    try:
        if query_type == "team_results":
            team_name = parsed.get("team")
            matches = await _fetch_team_matches(team_name)
            if matches:
                return _format_team_results(team_name, matches)
            else:
                return f"❌ Impossibile recuperare i risultati per {team_name}. Riprova tra poco."

        elif query_type == "next_matches":
            team_name = parsed.get("team")
            matches = await _fetch_next_matches(team_name)
            if matches:
                return _format_next_matches(team_name, matches)
            else:
                return f"❌ Impossibile recuperare le prossime partite per {team_name}."

        elif query_type == "standings":
            league_name = parsed.get("league")
            league_id = parsed.get("league_id")
            if league_id:
                standings = await _fetch_league_standings(league_id)
                if standings:
                    return _format_standings(league_name, standings)
            return f"❌ Classifica {league_name} non disponibile. Potrebbe servire una API key per football-data.org."

    except Exception as e:
        log.error(f"Sports agent error: {e}")
        return f"❌ Errore nel recupero dati sportivi: {e}"

    return None


async def get_sports_for_query(query: str) -> Optional[str]:
    """
    Wrapper: verifica se è una sports query e restituisce la risposta.
    """
    if not is_sports_query(query):
        return None

    return await get_sports_answer(query)
