#!/usr/bin/env python3
"""
agents/trading_agent.py
=======================

Agente trading dedicato per Jarvis.
Gestisce query su analisi tecnica, risk management, portfolio.

Funzionalità:
- Calcolo position size e risk/reward
- Analisi supporti e resistenze
- Calcolo stop loss e take profit
- Gestione portafoglio e allocazione
- Concetti di leva e margin

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

TRADING_API_TIMEOUT = float(os.getenv("TRADING_API_TIMEOUT", "10.0"))

# ===================== CALCULATION FUNCTIONS =====================


def calculate_position_size(
    account_size: float,
    risk_percent: float,
    entry_price: float,
    stop_loss_price: float,
) -> Dict[str, Any]:
    """
    Calcola la dimensione della posizione basata sul rischio.
    
    Args:
        account_size: Dimensione del conto
        risk_percent: Percentuale di rischio per trade (es. 2%)
        entry_price: Prezzo di entrata
        stop_loss_price: Prezzo dello stop loss
    
    Returns:
        Dict con position size e dettagli
    """
    if account_size <= 0 or risk_percent <= 0:
        return {"error": "Account size e risk devono essere positivi"}
    
    if entry_price <= 0 or stop_loss_price <= 0:
        return {"error": "I prezzi devono essere positivi"}
    
    # Calcola importo a rischio
    risk_amount = account_size * (risk_percent / 100)
    
    # Calcola distanza stop loss in percentuale
    if entry_price > stop_loss_price:  # Long position
        sl_distance = entry_price - stop_loss_price
        sl_distance_pct = (sl_distance / entry_price) * 100
        direction = "LONG"
    else:  # Short position
        sl_distance = stop_loss_price - entry_price
        sl_distance_pct = (sl_distance / entry_price) * 100
        direction = "SHORT"
    
    if sl_distance <= 0:
        return {"error": "Stop loss non valido per questa direzione"}
    
    # Position size = Risk Amount / SL Distance
    position_size_units = risk_amount / sl_distance
    position_value = position_size_units * entry_price
    
    return {
        "position_size_units": round(position_size_units, 4),
        "position_value": round(position_value, 2),
        "risk_amount": round(risk_amount, 2),
        "sl_distance": round(sl_distance, 4),
        "sl_distance_pct": round(sl_distance_pct, 2),
        "direction": direction,
        "entry_price": entry_price,
        "stop_loss": stop_loss_price,
    }


def calculate_risk_reward(
    entry_price: float,
    stop_loss: float,
    take_profit: float,
) -> Dict[str, Any]:
    """
    Calcola il rapporto Risk/Reward.
    """
    if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
        return {"error": "I prezzi devono essere positivi"}
    
    # Determina direzione
    if entry_price > stop_loss:  # Long
        risk = entry_price - stop_loss
        reward = take_profit - entry_price
        direction = "LONG"
    else:  # Short
        risk = stop_loss - entry_price
        reward = entry_price - take_profit
        direction = "SHORT"
    
    if risk <= 0 or reward <= 0:
        return {"error": "Configurazione SL/TP non valida per questa direzione"}
    
    rr_ratio = reward / risk
    
    # Calcola win rate necessario per break-even
    # Win Rate = 1 / (1 + R:R)
    breakeven_winrate = (1 / (1 + rr_ratio)) * 100
    
    return {
        "risk": round(risk, 4),
        "reward": round(reward, 4),
        "rr_ratio": round(rr_ratio, 2),
        "rr_display": f"1:{rr_ratio:.2f}",
        "breakeven_winrate": round(breakeven_winrate, 1),
        "direction": direction,
        "entry": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
    }


def calculate_compound_growth(
    initial: float,
    monthly_return_pct: float,
    months: int,
    monthly_contribution: float = 0,
) -> Dict[str, Any]:
    """
    Calcola crescita composta del portafoglio.
    """
    if initial <= 0 or months <= 0:
        return {"error": "Valori non validi"}
    
    monthly_rate = monthly_return_pct / 100
    current = initial
    
    for _ in range(months):
        current = current * (1 + monthly_rate) + monthly_contribution
    
    total_gain = current - initial - (monthly_contribution * months)
    total_invested = initial + (monthly_contribution * months)
    
    return {
        "final_value": round(current, 2),
        "initial": initial,
        "total_invested": round(total_invested, 2),
        "total_gain": round(total_gain, 2),
        "gain_pct": round((total_gain / total_invested) * 100, 2),
        "months": months,
        "monthly_return": monthly_return_pct,
    }


def calculate_leverage_impact(
    position_value: float,
    leverage: float,
    price_change_pct: float,
) -> Dict[str, Any]:
    """
    Calcola l'impatto della leva su un trade.
    """
    if leverage <= 0:
        return {"error": "Leva deve essere positiva"}
    
    # Margin richiesto
    margin_required = position_value / leverage
    
    # Profitto/perdita senza leva
    pnl_no_leverage = position_value * (price_change_pct / 100)
    pnl_pct_no_leverage = price_change_pct
    
    # Profitto/perdita con leva (sul capitale investito)
    pnl_with_leverage = pnl_no_leverage  # Il PnL in $ è lo stesso
    pnl_pct_with_leverage = (pnl_with_leverage / margin_required) * 100
    
    # Prezzo di liquidazione (approssimato)
    liquidation_change_pct = 100 / leverage
    
    return {
        "position_value": position_value,
        "margin_required": round(margin_required, 2),
        "leverage": leverage,
        "price_change_pct": price_change_pct,
        "pnl_dollars": round(pnl_with_leverage, 2),
        "pnl_on_margin_pct": round(pnl_pct_with_leverage, 2),
        "liquidation_approx_pct": round(liquidation_change_pct, 2),
    }


# ===================== QUERY EXTRACTION =====================


def extract_trading_params(query: str) -> Dict[str, Any]:
    """
    Estrae parametri di trading dalla query.
    """
    q = query.lower().strip()
    params: Dict[str, Any] = {}
    
    # Cerca prezzi (entry, sl, tp)
    entry_match = re.search(r"entr[yi]\s*[:=]?\s*(\d+(?:[.,]\d+)?)", q)
    if entry_match:
        params["entry_price"] = float(entry_match.group(1).replace(",", "."))
    
    sl_match = re.search(r"(?:stop\s*loss|sl)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", q)
    if sl_match:
        params["stop_loss"] = float(sl_match.group(1).replace(",", "."))
    
    tp_match = re.search(r"(?:take\s*profit|tp)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", q)
    if tp_match:
        params["take_profit"] = float(tp_match.group(1).replace(",", "."))
    
    # Cerca account size / capitale
    account_match = re.search(r"(?:account|capitale|conto)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", q)
    if account_match:
        params["account_size"] = float(account_match.group(1).replace(",", "."))
    
    # Cerca risk %
    risk_match = re.search(r"(?:risk|rischio)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*%?", q)
    if risk_match:
        params["risk_percent"] = float(risk_match.group(1).replace(",", "."))
    
    # Cerca leva
    leverage_match = re.search(r"(?:leva|leverage)\s*[:=]?\s*(\d+)x?", q)
    if leverage_match:
        params["leverage"] = float(leverage_match.group(1))
    
    # Determina tipo di richiesta
    if any(kw in q for kw in ["position size", "size posizione", "quante unità", "quanto comprare"]):
        params["request_type"] = "position_size"
    elif any(kw in q for kw in ["risk reward", "r:r", "rr", "rischio rendimento"]):
        params["request_type"] = "risk_reward"
    elif any(kw in q for kw in ["leva", "leverage", "margin"]):
        params["request_type"] = "leverage"
    elif any(kw in q for kw in ["compound", "crescita", "portafoglio"]):
        params["request_type"] = "compound"
    else:
        params["request_type"] = "general"
    
    return params


def is_trading_query(query: str) -> bool:
    """
    Determina se la query è una richiesta di trading.
    """
    q = query.lower().strip()
    
    trading_keywords = [
        "trading", "trader", "trade",
        "long", "short", "buy signal", "sell signal",
        "stop loss", "take profit", "tp", "sl",
        "leva", "leverage", "margin",
        "analisi tecnica", "technical analysis",
        "supporto", "resistenza", "support", "resistance",
        "position size", "risk reward",
        "portafoglio", "portfolio", "allocazione",
    ]
    
    return any(kw in q for kw in trading_keywords)


# ===================== FORMATTERS =====================


def format_position_size_response(params: Dict[str, Any], result: Dict[str, Any]) -> str:
    """
    Formatta risposta calcolo position size.
    """
    lines = ["📊 **Calcolo Position Size**\n"]
    
    lines.append("**✅ Input:**")
    lines.append(f"• Account size: **€{params.get('account_size', 0):,.0f}**")
    lines.append(f"• Rischio per trade: **{params.get('risk_percent', 0)}%**")
    lines.append(f"• Entry price: **{result.get('entry_price', 0)}**")
    lines.append(f"• Stop loss: **{result.get('stop_loss', 0)}**")
    
    lines.append("\n**📈 Risultati:**")
    lines.append(f"• Direzione: **{result.get('direction', 'N/A')}**")
    lines.append(f"• Position size: **{result.get('position_size_units', 0):.4f} unità**")
    lines.append(f"• Valore posizione: **€{result.get('position_value', 0):,.2f}**")
    lines.append(f"• Importo a rischio: **€{result.get('risk_amount', 0):.2f}**")
    lines.append(f"• Distanza SL: **{result.get('sl_distance_pct', 0):.2f}%**")
    
    lines.append("\n**⚠️ Note:**")
    lines.append("• Questo calcolo presuppone un rischio fisso per trade.")
    lines.append("• Adatta sempre alle condizioni di mercato.")
    
    lines.append(f"\n📡 Calcolato: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    return "\n".join(lines)


def format_risk_reward_response(params: Dict[str, Any], result: Dict[str, Any]) -> str:
    """
    Formatta risposta calcolo Risk/Reward.
    """
    lines = ["📐 **Calcolo Risk/Reward**\n"]
    
    lines.append("**✅ Input:**")
    lines.append(f"• Entry: **{result.get('entry', 0)}**")
    lines.append(f"• Stop Loss: **{result.get('stop_loss', 0)}**")
    lines.append(f"• Take Profit: **{result.get('take_profit', 0)}**")
    
    lines.append("\n**📊 Risultati:**")
    lines.append(f"• Direzione: **{result.get('direction', 'N/A')}**")
    lines.append(f"• Risk: **{result.get('risk', 0):.4f}**")
    lines.append(f"• Reward: **{result.get('reward', 0):.4f}**")
    lines.append(f"• R:R Ratio: **{result.get('rr_display', 'N/A')}**")
    
    rr = result.get("rr_ratio", 0)
    if rr >= 3:
        lines.append("\n**✅ Ottimo R:R!** Target consigliato: almeno 1:3")
    elif rr >= 2:
        lines.append("\n**👍 Buon R:R.** Accettabile per la maggior parte delle strategie.")
    elif rr >= 1:
        lines.append("\n**⚠️ R:R basso.** Richiede win rate > 50% per profitto.")
    else:
        lines.append("\n**❌ R:R sfavorevole.** Considera di rivedere i livelli.")
    
    lines.append(f"\n**📖 Win rate necessario per break-even:** {result.get('breakeven_winrate', 0):.1f}%")
    
    lines.append(f"\n📡 Calcolato: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    return "\n".join(lines)


def format_leverage_response(params: Dict[str, Any], result: Dict[str, Any]) -> str:
    """
    Formatta risposta calcolo leva.
    """
    lines = ["⚡ **Calcolo Impatto Leva**\n"]
    
    lines.append("**✅ Input:**")
    lines.append(f"• Posizione: **€{result.get('position_value', 0):,.0f}**")
    lines.append(f"• Leva: **{result.get('leverage', 0)}x**")
    lines.append(f"• Variazione prezzo: **{result.get('price_change_pct', 0):+.1f}%**")
    
    lines.append("\n**📊 Risultati:**")
    lines.append(f"• Margin richiesto: **€{result.get('margin_required', 0):,.2f}**")
    lines.append(f"• P/L in €: **€{result.get('pnl_dollars', 0):+,.2f}**")
    lines.append(f"• P/L su margin: **{result.get('pnl_on_margin_pct', 0):+.1f}%**")
    
    lines.append("\n**⚠️ Rischio Liquidazione:**")
    lines.append(f"• Con leva {result.get('leverage', 0)}x, circa **{result.get('liquidation_approx_pct', 0):.1f}%** di movimento avverso può liquidare la posizione.")
    
    lines.append("\n**⚠️ Avvertenze:**")
    lines.append("• La leva amplifica sia i guadagni che le perdite.")
    lines.append("• Usa sempre stop loss con posizioni a leva.")
    
    lines.append(f"\n📡 Calcolato: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    return "\n".join(lines)


def format_general_trading_response(query: str) -> str:
    """
    Formatta risposta educativa generale su trading.
    """
    lines = ["📈 **Guida Trading & Risk Management**\n"]
    
    lines.append("**📚 Concetti chiave:**\n")
    
    lines.append("**1. Position Sizing**")
    lines.append("   Calcola quanto investire in ogni trade basandoti sul")
    lines.append("   rischio massimo che vuoi assumere (es. 1-2% del conto).\n")
    
    lines.append("**2. Risk/Reward (R:R)**")
    lines.append("   Rapporto tra potenziale perdita e potenziale guadagno.")
    lines.append("   Target minimo consigliato: 1:2 o superiore.\n")
    
    lines.append("**3. Stop Loss**")
    lines.append("   Livello di prezzo dove chiudi automaticamente la posizione")
    lines.append("   per limitare le perdite. Mai fare trading senza SL.\n")
    
    lines.append("**4. Leva Finanziaria**")
    lines.append("   Amplifica i movimenti. Leva 10x = guadagni/perdite x10.")
    lines.append("   Usa con cautela, specialmente se principiante.\n")
    
    lines.append("**🔢 Come usarmi:**")
    lines.append("• `position size account 10000 risk 2% entry 100 sl 95`")
    lines.append("• `risk reward entry 100 sl 95 tp 115`")
    lines.append("• `impatto leva 10x su 1000€ con movimento 5%`")
    
    lines.append("\n**⚠️ Disclaimer:**")
    lines.append("• Il trading comporta rischi significativi.")
    lines.append("• Non fornisco consigli finanziari personalizzati.")
    lines.append("• Studia, fai paper trading, poi opera con cautela.")
    
    return "\n".join(lines)


# ===================== PUBLIC API =====================


async def get_trading_answer(query: str) -> Optional[str]:
    """
    API principale: data una query trading, restituisce la risposta.
    """
    params = extract_trading_params(query)
    request_type = params.get("request_type", "general")
    
    try:
        if request_type == "position_size":
            required = ["account_size", "risk_percent", "entry_price", "stop_loss"]
            missing = [k for k in required if k not in params]
            if missing:
                return (
                    f"❌ Per calcolare il position size mi servono: {', '.join(missing)}.\n\n"
                    "Esempio: `position size account 10000 risk 2% entry 100 sl 95`"
                )
            result = calculate_position_size(
                account_size=params["account_size"],
                risk_percent=params["risk_percent"],
                entry_price=params["entry_price"],
                stop_loss_price=params["stop_loss"],
            )
            if "error" in result:
                return f"❌ Errore: {result['error']}"
            return format_position_size_response(params, result)
        
        elif request_type == "risk_reward":
            required = ["entry_price", "stop_loss", "take_profit"]
            missing = [k for k in required if k not in params]
            if missing:
                return (
                    f"❌ Per calcolare R:R mi servono: {', '.join(missing)}.\n\n"
                    "Esempio: `risk reward entry 100 sl 95 tp 115`"
                )
            result = calculate_risk_reward(
                entry_price=params["entry_price"],
                stop_loss=params["stop_loss"],
                take_profit=params["take_profit"],
            )
            if "error" in result:
                return f"❌ Errore: {result['error']}"
            return format_risk_reward_response(params, result)
        
        elif request_type == "leverage":
            # Cerca valori nella query in modo più flessibile
            if "leverage" not in params:
                return (
                    "❌ Per calcolare l'impatto della leva mi serve il valore della leva.\n\n"
                    "Esempio: `impatto leva 10x su 1000€ con movimento 5%`"
                )
            
            # Valori di default se non specificati
            position = params.get("account_size", 1000)
            price_change = 5  # Default 5% se non specificato
            
            result = calculate_leverage_impact(
                position_value=position,
                leverage=params["leverage"],
                price_change_pct=price_change,
            )
            if "error" in result:
                return f"❌ Errore: {result['error']}"
            return format_leverage_response(params, result)
        
        else:
            # Risposta educativa generale
            return format_general_trading_response(query)
    
    except Exception as e:
        log.error(f"Trading agent error: {e}")
        return f"❌ Errore nel calcolo: {e}"


async def get_trading_for_query(query: str) -> Optional[str]:
    """
    Wrapper: verifica se è una trading query e restituisce la risposta.
    """
    if not is_trading_query(query):
        return None
    
    return await get_trading_answer(query)
