#!/usr/bin/env python3
"""
agents/betting_agent.py
=======================

Agente betting dedicato per Jarvis.
Gestisce query su scommesse, quote, value bet, calcoli EV.

Funzionalità:
- Calcolo Expected Value (EV)
- Calcolo Kelly Criterion
- Analisi value bet
- Confronto quote
- Gestione bankroll

API usate:
- Odds API (opzionale) - per quote live
- Fallback: calcoli educativi senza dati live

Formato risposta standardizzato:
- Emoji + titolo
- Blocco dati/calcoli (✅)
- Blocco analisi/consigli (⚠️)
- Fonte con timestamp
"""

import asyncio
import logging
import re
import os
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import math

log = logging.getLogger(__name__)

# ===================== CONFIG =====================

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
BETTING_API_TIMEOUT = float(os.getenv("BETTING_API_TIMEOUT", "10.0"))

# ===================== CONSTANTS =====================

# Formato quote comuni
ODDS_FORMATS = {
    "decimal": "Decimali (EU)",
    "fractional": "Frazionarie (UK)",
    "american": "Americane (US)",
}

# ===================== CALCULATION FUNCTIONS =====================


def decimal_to_probability(odds: float) -> float:
    """
    Converte quota decimale in probabilità implicita.
    
    Args:
        odds: Quota decimale (es. 2.50)
    
    Returns:
        Probabilità implicita (0-1)
    """
    if odds <= 0:
        return 0.0
    return 1.0 / odds


def calculate_ev(odds: float, probability: float, stake: float = 100) -> Dict[str, Any]:
    """
    Calcola Expected Value (EV) per una scommessa.
    
    Args:
        odds: Quota decimale
        probability: Probabilità stimata di vittoria (0-1)
        stake: Importo scommessa
    
    Returns:
        Dict con EV, ROI, e analisi
    """
    if odds <= 0 or probability <= 0 or probability > 1:
        return {
            "ev": 0,
            "roi": 0,
            "is_value": False,
            "error": "Parametri non validi",
        }
    
    # EV = (Probabilità × (Quota - 1) × Stake) - ((1 - Probabilità) × Stake)
    win_amount = stake * (odds - 1)
    ev = (probability * win_amount) - ((1 - probability) * stake)
    roi = ev / stake * 100
    
    # Valore se EV > 0
    is_value = ev > 0
    
    # Probabilità implicita del bookmaker
    implied_prob = decimal_to_probability(odds)
    edge = (probability - implied_prob) * 100
    
    return {
        "ev": round(ev, 2),
        "roi": round(roi, 2),
        "is_value": is_value,
        "edge": round(edge, 2),
        "implied_probability": round(implied_prob * 100, 2),
        "your_probability": round(probability * 100, 2),
        "stake": stake,
        "odds": odds,
    }


def calculate_kelly(odds: float, probability: float, fraction: float = 0.25) -> Dict[str, Any]:
    """
    Calcola stake ottimale con Kelly Criterion.
    
    Args:
        odds: Quota decimale
        probability: Probabilità stimata di vittoria (0-1)
        fraction: Frazione di Kelly da usare (default 0.25 = quarter Kelly)
    
    Returns:
        Dict con Kelly stake percentuale
    """
    if odds <= 1 or probability <= 0 or probability >= 1:
        return {
            "kelly_full": 0,
            "kelly_fraction": 0,
            "recommended_stake_pct": 0,
            "error": "Parametri non validi",
        }
    
    # Kelly = (p × b - q) / b
    # dove p = probabilità vittoria, q = 1-p, b = odds - 1
    b = odds - 1
    q = 1 - probability
    
    kelly_full = (probability * b - q) / b
    
    # Se Kelly negativo, non scommettere
    if kelly_full <= 0:
        return {
            "kelly_full": 0,
            "kelly_fraction": 0,
            "recommended_stake_pct": 0,
            "edge": round((probability - decimal_to_probability(odds)) * 100, 2),
            "note": "Kelly negativo: nessun vantaggio, non scommettere",
        }
    
    kelly_fractional = kelly_full * fraction
    
    return {
        "kelly_full": round(kelly_full * 100, 2),
        "kelly_fraction": round(kelly_fractional * 100, 2),
        "fraction_used": fraction,
        "recommended_stake_pct": round(kelly_fractional * 100, 2),
        "edge": round((probability - decimal_to_probability(odds)) * 100, 2),
    }


def american_to_decimal(american_odds: int) -> float:
    """Converte quote americane in decimali."""
    if american_odds > 0:
        return (american_odds / 100) + 1
    else:
        return (100 / abs(american_odds)) + 1


def fractional_to_decimal(num: int, den: int) -> float:
    """Converte quote frazionarie in decimali."""
    return (num / den) + 1


# ===================== QUERY EXTRACTION =====================


def extract_betting_params(query: str) -> Dict[str, Any]:
    """
    Estrae parametri di betting dalla query.
    """
    q = query.lower().strip()
    params: Dict[str, Any] = {}
    
    # Cerca quota decimale (es. 2.50, 1.85)
    odds_match = re.search(r"quota[:\s]+(\d+[.,]\d+)|(\d+[.,]\d+)\s*quota", q)
    if odds_match:
        odds_str = odds_match.group(1) or odds_match.group(2)
        params["odds"] = float(odds_str.replace(",", "."))
    else:
        # Cerca qualsiasi numero decimale > 1 che potrebbe essere una quota
        decimal_match = re.search(r"\b(\d+[.,]\d{2})\b", q)
        if decimal_match:
            val = float(decimal_match.group(1).replace(",", "."))
            if 1.01 <= val <= 100:  # Range ragionevole per quote
                params["odds"] = val
    
    # Cerca probabilità (es. 60%, prob 0.6)
    prob_match = re.search(r"(\d+)[%]|\bprob(?:abilit[aà])?\s*[:=]?\s*(\d+(?:[.,]\d+)?)", q)
    if prob_match:
        prob_str = prob_match.group(1) or prob_match.group(2)
        prob_val = float(prob_str.replace(",", "."))
        if prob_val > 1:  # Percentuale
            params["probability"] = prob_val / 100
        else:
            params["probability"] = prob_val
    
    # Cerca stake (es. 100€, stake 50)
    stake_match = re.search(r"stake\s*[:=]?\s*(\d+)|(\d+)\s*[€$]", q)
    if stake_match:
        params["stake"] = float(stake_match.group(1) or stake_match.group(2))
    
    # Determina tipo di richiesta
    if any(kw in q for kw in ["ev", "expected value", "valore atteso"]):
        params["request_type"] = "ev"
    elif any(kw in q for kw in ["kelly", "stake ottimale", "quanto puntare"]):
        params["request_type"] = "kelly"
    elif any(kw in q for kw in ["value bet", "valuebet", "valore"]):
        params["request_type"] = "value"
    elif any(kw in q for kw in ["converti", "conversione", "convert"]):
        params["request_type"] = "convert"
    else:
        params["request_type"] = "general"
    
    return params


def is_betting_query(query: str) -> bool:
    """
    Determina se la query è una richiesta di betting.
    """
    q = query.lower().strip()
    
    betting_keywords = [
        "scommessa", "scommesse", "bet", "betting",
        "quote", "odds", "pronostico", "pronostici",
        "value bet", "over", "under", "handicap",
        "expected value", "ev", "kelly",
        "bookmaker", "bookie", "quota",
        "quanto puntare", "stake",
    ]
    
    return any(kw in q for kw in betting_keywords)


# ===================== FORMATTERS =====================


def format_ev_response(params: Dict[str, Any], result: Dict[str, Any]) -> str:
    """
    Formatta risposta calcolo EV.
    """
    lines = ["🎰 **Calcolo Expected Value (EV)**\n"]
    
    lines.append("**✅ Input:**")
    lines.append(f"• Quota: **{params.get('odds', 'N/A')}**")
    lines.append(f"• Probabilità stimata: **{params.get('probability', 0) * 100:.1f}%**")
    lines.append(f"• Stake: **€{params.get('stake', 100):.0f}**")
    
    lines.append("\n**📊 Risultati:**")
    lines.append(f"• Expected Value: **€{result.get('ev', 0):.2f}**")
    lines.append(f"• ROI atteso: **{result.get('roi', 0):.2f}%**")
    lines.append(f"• Edge: **{result.get('edge', 0):+.2f}%**")
    lines.append(f"• Prob. implicita bookmaker: **{result.get('implied_probability', 0):.1f}%**")
    
    # Verdetto
    if result.get("is_value"):
        lines.append("\n**✅ Verdetto:** Value Bet! (EV positivo)")
        lines.append("  → La tua stima di probabilità è superiore a quella del bookmaker.")
    else:
        lines.append("\n**❌ Verdetto:** Non è value (EV negativo)")
        lines.append("  → Il bookmaker ha un vantaggio su questa scommessa.")
    
    lines.append("\n**⚠️ Nota:**")
    lines.append("• I calcoli sono educativi. La stima di probabilità è cruciale.")
    lines.append("• Scommetti responsabilmente e solo ciò che puoi permetterti di perdere.")
    
    lines.append(f"\n📡 Calcolato: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    return "\n".join(lines)


def format_kelly_response(params: Dict[str, Any], result: Dict[str, Any]) -> str:
    """
    Formatta risposta calcolo Kelly.
    """
    lines = ["📐 **Calcolo Kelly Criterion**\n"]
    
    lines.append("**✅ Input:**")
    lines.append(f"• Quota: **{params.get('odds', 'N/A')}**")
    lines.append(f"• Probabilità stimata: **{params.get('probability', 0) * 100:.1f}%**")
    
    lines.append("\n**📊 Risultati:**")
    lines.append(f"• Kelly Full: **{result.get('kelly_full', 0):.2f}%** del bankroll")
    lines.append(f"• Quarter Kelly (consigliato): **{result.get('kelly_fraction', 0):.2f}%** del bankroll")
    lines.append(f"• Edge stimato: **{result.get('edge', 0):+.2f}%**")
    
    if result.get("kelly_full", 0) > 0:
        lines.append("\n**💡 Esempio pratico:**")
        bankroll = 1000
        stake = bankroll * result.get("kelly_fraction", 0) / 100
        lines.append(f"  Con bankroll €{bankroll}: punta **€{stake:.2f}**")
    else:
        lines.append("\n**⚠️ Kelly negativo:**")
        lines.append("  Non c'è vantaggio. Consiglio: non scommettere.")
    
    lines.append("\n**📖 Formula Kelly:**")
    lines.append("  `f = (p × b - q) / b`")
    lines.append("  dove p=prob. vittoria, q=prob. perdita, b=quota-1")
    
    lines.append("\n**⚠️ Nota:**")
    lines.append("• Il Kelly presuppone una stima accurata della probabilità.")
    lines.append("• Usa Quarter/Half Kelly per ridurre varianza.")
    
    lines.append(f"\n📡 Calcolato: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    return "\n".join(lines)


def format_general_betting_response(query: str) -> str:
    """
    Formatta risposta educativa generale su betting.
    """
    lines = ["🎰 **Guida Betting & Value**\n"]
    
    lines.append("**📚 Concetti chiave:**\n")
    
    lines.append("**1. Expected Value (EV)**")
    lines.append("   EV = (Prob × Vincita) - ((1-Prob) × Stake)")
    lines.append("   Se EV > 0, la scommessa ha valore nel lungo periodo.\n")
    
    lines.append("**2. Value Bet**")
    lines.append("   Una scommessa dove la tua stima di probabilità è")
    lines.append("   superiore a quella implicita nella quota del bookmaker.\n")
    
    lines.append("**3. Kelly Criterion**")
    lines.append("   Formula matematica per calcolare lo stake ottimale")
    lines.append("   che massimizza la crescita del bankroll.\n")
    
    lines.append("**🔢 Come usarmi:**")
    lines.append("• `calcola ev quota 2.50 probabilità 45%`")
    lines.append("• `kelly quota 1.85 prob 60%`")
    lines.append("• `è value bet quota 2.10 prob 50%?`")
    
    lines.append("\n**⚠️ Disclaimer:**")
    lines.append("• Il betting comporta rischi. Gioca responsabilmente.")
    lines.append("• Non fornisco pronostici o consigli specifici.")
    lines.append("• Usa questi strumenti solo a scopo educativo.")
    
    return "\n".join(lines)


# ===================== PUBLIC API =====================


async def get_betting_answer(query: str) -> Optional[str]:
    """
    API principale: data una query betting, restituisce la risposta.
    """
    params = extract_betting_params(query)
    request_type = params.get("request_type", "general")
    
    try:
        if request_type == "ev":
            if "odds" not in params or "probability" not in params:
                return (
                    "❌ Per calcolare l'EV mi servono quota e probabilità.\n\n"
                    "Esempio: `calcola ev quota 2.50 probabilità 45%`"
                )
            result = calculate_ev(
                odds=params["odds"],
                probability=params["probability"],
                stake=params.get("stake", 100),
            )
            return format_ev_response(params, result)
        
        elif request_type == "kelly":
            if "odds" not in params or "probability" not in params:
                return (
                    "❌ Per calcolare il Kelly mi servono quota e probabilità.\n\n"
                    "Esempio: `kelly quota 1.85 prob 60%`"
                )
            result = calculate_kelly(
                odds=params["odds"],
                probability=params["probability"],
            )
            return format_kelly_response(params, result)
        
        elif request_type == "value":
            if "odds" not in params or "probability" not in params:
                return (
                    "❌ Per verificare una value bet mi servono quota e probabilità.\n\n"
                    "Esempio: `è value bet quota 2.10 prob 50%?`"
                )
            result = calculate_ev(
                odds=params["odds"],
                probability=params["probability"],
            )
            return format_ev_response(params, result)
        
        else:
            # Risposta educativa generale
            return format_general_betting_response(query)
    
    except Exception as e:
        log.error(f"Betting agent error: {e}")
        return f"❌ Errore nel calcolo: {e}"


async def get_betting_for_query(query: str) -> Optional[str]:
    """
    Wrapper: verifica se è una betting query e restituisce la risposta.
    """
    if not is_betting_query(query):
        return None
    
    return await get_betting_answer(query)
