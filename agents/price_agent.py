#!/usr/bin/env python3
"""
agents/price_agent.py
=====================

Agente prezzi dedicato per Jarvis.
Gestisce query su prezzi crypto, azioni, indici, forex.

API gratuite usate:
- CoinGecko API (crypto) - no API key
- Alpha Vantage (azioni/forex) - API key opzionale

Formato risposta standardizzato:
- Emoji + titolo
- Blocco dati verificati (✅)
- Blocco analisi/commenti (⚠️)
- Fonte con timestamp
"""

import asyncio
import logging
import re
import os
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

log = logging.getLogger(__name__)

# ===================== CONFIG =====================

# API Keys (opzionali - alcune API funzionano senza)
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "demo")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")  # Pro key se disponibile

# Timeout per le chiamate API
PRICE_API_TIMEOUT = float(os.getenv("PRICE_API_TIMEOUT", "8.0"))

# ===================== ASSET MAPPING =====================

# Mapping nomi comuni → simboli crypto (CoinGecko IDs)
CRYPTO_ALIASES: Dict[str, str] = {
    # Bitcoin
    "bitcoin": "bitcoin",
    "btc": "bitcoin",
    # Ethereum
    "ethereum": "ethereum",
    "eth": "ethereum",
    "ether": "ethereum",
    # Solana
    "solana": "solana",
    "sol": "solana",
    # Altre crypto popolari
    "ripple": "ripple",
    "xrp": "ripple",
    "cardano": "cardano",
    "ada": "cardano",
    "dogecoin": "dogecoin",
    "doge": "dogecoin",
    "polkadot": "polkadot",
    "dot": "polkadot",
    "polygon": "matic-network",
    "matic": "matic-network",
    "avalanche": "avalanche-2",
    "avax": "avalanche-2",
    "chainlink": "chainlink",
    "link": "chainlink",
    "uniswap": "uniswap",
    "uni": "uniswap",
    "litecoin": "litecoin",
    "ltc": "litecoin",
    "binance coin": "binancecoin",
    "bnb": "binancecoin",
    "tether": "tether",
    "usdt": "tether",
    "usdc": "usd-coin",
    "shiba": "shiba-inu",
    "shib": "shiba-inu",
    "tron": "tron",
    "trx": "tron",
    "cosmos": "cosmos",
    "atom": "cosmos",
    "near": "near",
    "near protocol": "near",
    "aptos": "aptos",
    "apt": "aptos",
    "arbitrum": "arbitrum",
    "arb": "arbitrum",
    "sui": "sui",
    "pepe": "pepe",
}

# Mapping indici e azioni popolari (Alpha Vantage symbols)
STOCK_ALIASES: Dict[str, Tuple[str, str]] = {
    # Indici USA
    "s&p 500": ("SPY", "S&P 500 ETF"),
    "s&p500": ("SPY", "S&P 500 ETF"),
    "sp500": ("SPY", "S&P 500 ETF"),
    "nasdaq": ("QQQ", "NASDAQ 100 ETF"),
    "nasdaq 100": ("QQQ", "NASDAQ 100 ETF"),
    "dow jones": ("DIA", "Dow Jones ETF"),
    "dow": ("DIA", "Dow Jones ETF"),
    # Tech stocks
    "apple": ("AAPL", "Apple Inc."),
    "aapl": ("AAPL", "Apple Inc."),
    "microsoft": ("MSFT", "Microsoft Corp."),
    "msft": ("MSFT", "Microsoft Corp."),
    "google": ("GOOGL", "Alphabet Inc."),
    "googl": ("GOOGL", "Alphabet Inc."),
    "amazon": ("AMZN", "Amazon.com Inc."),
    "amzn": ("AMZN", "Amazon.com Inc."),
    "tesla": ("TSLA", "Tesla Inc."),
    "tsla": ("TSLA", "Tesla Inc."),
    "nvidia": ("NVDA", "NVIDIA Corp."),
    "nvda": ("NVDA", "NVIDIA Corp."),
    "meta": ("META", "Meta Platforms Inc."),
    "facebook": ("META", "Meta Platforms Inc."),
    # Altri
    "netflix": ("NFLX", "Netflix Inc."),
    "nflx": ("NFLX", "Netflix Inc."),
}

# Forex pairs
FOREX_ALIASES: Dict[str, Tuple[str, str, str]] = {
    # EUR pairs
    "eur/usd": ("EUR", "USD", "Euro/Dollaro USA"),
    "eurusd": ("EUR", "USD", "Euro/Dollaro USA"),
    "euro dollaro": ("EUR", "USD", "Euro/Dollaro USA"),
    "eur/gbp": ("EUR", "GBP", "Euro/Sterlina"),
    "eurgbp": ("EUR", "GBP", "Euro/Sterlina"),
    # GBP pairs
    "gbp/usd": ("GBP", "USD", "Sterlina/Dollaro USA"),
    "gbpusd": ("GBP", "USD", "Sterlina/Dollaro USA"),
    # USD pairs
    "usd/jpy": ("USD", "JPY", "Dollaro USA/Yen"),
    "usdjpy": ("USD", "JPY", "Dollaro USA/Yen"),
    "usd/chf": ("USD", "CHF", "Dollaro USA/Franco Svizzero"),
    "usdchf": ("USD", "CHF", "Dollaro USA/Franco Svizzero"),
    # Commodities
    "oro": ("XAU", "USD", "Oro/Dollaro USA"),
    "gold": ("XAU", "USD", "Oro/Dollaro USA"),
    "xauusd": ("XAU", "USD", "Oro/Dollaro USA"),
    "xau/usd": ("XAU", "USD", "Oro/Dollaro USA"),
    "argento": ("XAG", "USD", "Argento/Dollaro USA"),
    "silver": ("XAG", "USD", "Argento/Dollaro USA"),
    "xagusd": ("XAG", "USD", "Argento/Dollaro USA"),
}

# ===================== API CALLS =====================


async def _fetch_crypto_price(coin_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch prezzo crypto da CoinGecko API.
    Ritorna dati strutturati o None se fallisce.
    """
    try:
        import aiohttp

        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        }

        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-pro-api-key"] = COINGECKO_API_KEY

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=PRICE_API_TIMEOUT)
        ) as session:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    log.warning(f"CoinGecko API returned {resp.status} for {coin_id}")
                    return None

                data = await resp.json()
                market_data = data.get("market_data", {})

                if not market_data:
                    return None

                current_price = market_data.get("current_price", {})
                price_usd = current_price.get("usd")
                price_eur = current_price.get("eur")

                price_change_24h = market_data.get("price_change_percentage_24h")
                price_change_7d = market_data.get("price_change_percentage_7d")

                market_cap = market_data.get("market_cap", {}).get("usd")
                volume_24h = market_data.get("total_volume", {}).get("usd")

                ath = market_data.get("ath", {}).get("usd")
                ath_change = market_data.get("ath_change_percentage", {}).get("usd")

                return {
                    "type": "crypto",
                    "name": data.get("name", coin_id),
                    "symbol": (data.get("symbol") or "").upper(),
                    "price_usd": price_usd,
                    "price_eur": price_eur,
                    "change_24h": price_change_24h,
                    "change_7d": price_change_7d,
                    "market_cap": market_cap,
                    "volume_24h": volume_24h,
                    "ath": ath,
                    "ath_change": ath_change,
                    "source": "CoinGecko",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }

    except Exception as e:
        log.error(f"CoinGecko API error for {coin_id}: {e}")
        return None


async def _fetch_stock_price(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch prezzo azioni da Alpha Vantage API.
    Ritorna dati strutturati o None se fallisce.
    """
    try:
        import aiohttp

        url = "https://www.alphavantage.co/query"
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": ALPHA_VANTAGE_KEY,
        }

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=PRICE_API_TIMEOUT)
        ) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    log.warning(f"Alpha Vantage API returned {resp.status} for {symbol}")
                    return None

                data = await resp.json()

                # Check for rate limit or errors
                if "Note" in data or "Error Message" in data:
                    log.warning(f"Alpha Vantage API limit/error: {data}")
                    return None

                quote = data.get("Global Quote", {})
                if not quote:
                    return None

                price = float(quote.get("05. price", 0))
                change = float(quote.get("09. change", 0))
                change_pct_str = quote.get("10. change percent", "0%").replace("%", "")
                change_pct = float(change_pct_str) if change_pct_str else 0

                return {
                    "type": "stock",
                    "symbol": symbol,
                    "name": STOCK_ALIASES.get(symbol.lower(), (symbol, symbol))[1],
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "open": float(quote.get("02. open", 0)),
                    "high": float(quote.get("03. high", 0)),
                    "low": float(quote.get("04. low", 0)),
                    "volume": int(quote.get("06. volume", 0)),
                    "source": "Alpha Vantage",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }

    except Exception as e:
        log.error(f"Alpha Vantage API error for {symbol}: {e}")
        return None


async def _fetch_forex_rate(from_curr: str, to_curr: str) -> Optional[Dict[str, Any]]:
    """
    Fetch tasso di cambio forex da Alpha Vantage API.
    """
    try:
        import aiohttp

        url = "https://www.alphavantage.co/query"
        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": from_curr,
            "to_currency": to_curr,
            "apikey": ALPHA_VANTAGE_KEY,
        }

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=PRICE_API_TIMEOUT)
        ) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    log.warning(
                        f"Alpha Vantage Forex API returned {resp.status} for {from_curr}/{to_curr}"
                    )
                    return None

                data = await resp.json()

                if "Note" in data or "Error Message" in data:
                    log.warning(f"Alpha Vantage Forex limit/error: {data}")
                    return None

                rate_data = data.get("Realtime Currency Exchange Rate", {})
                if not rate_data:
                    return None

                rate = float(rate_data.get("5. Exchange Rate", 0))

                return {
                    "type": "forex",
                    "from": from_curr,
                    "to": to_curr,
                    "pair": f"{from_curr}/{to_curr}",
                    "rate": rate,
                    "bid": float(rate_data.get("8. Bid Price", rate)),
                    "ask": float(rate_data.get("9. Ask Price", rate)),
                    "source": "Alpha Vantage",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }

    except Exception as e:
        log.error(f"Alpha Vantage Forex error for {from_curr}/{to_curr}: {e}")
        return None


# ===================== FORMATTERS =====================


def _format_number(n: float, decimals: int = 2) -> str:
    """Formatta numeri grandi in modo leggibile."""
    if n is None:
        return "N/A"
    if abs(n) >= 1_000_000_000_000:
        return f"${n/1_000_000_000_000:.2f}T"
    if abs(n) >= 1_000_000_000:
        return f"${n/1_000_000_000:.2f}B"
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n/1_000:.2f}K"
    return f"${n:,.{decimals}f}"


def _format_change(change: Optional[float]) -> str:
    """Formatta variazione percentuale con emoji."""
    if change is None:
        return "N/A"
    emoji = "📈" if change >= 0 else "📉"
    sign = "+" if change >= 0 else ""
    return f"{emoji} {sign}{change:.2f}%"


def _format_crypto_response(data: Dict[str, Any]) -> str:
    """
    Formatta risposta crypto in stile Jarvis standardizzato.
    """
    name = data.get("name", "Crypto")
    symbol = data.get("symbol", "")
    price_usd = data.get("price_usd")
    price_eur = data.get("price_eur")
    change_24h = data.get("change_24h")
    change_7d = data.get("change_7d")
    market_cap = data.get("market_cap")
    volume_24h = data.get("volume_24h")
    ath = data.get("ath")
    ath_change = data.get("ath_change")
    source = data.get("source", "CoinGecko")
    timestamp = data.get("timestamp", "")

    lines = [f"📈 **Prezzo {name} ({symbol})** – aggiornamento live\n"]

    # Blocco dati verificati
    lines.append("**✅ Dati verificati:**")

    if price_usd is not None:
        lines.append(f"• Prezzo attuale: **${price_usd:,.4f}**")
    if price_eur is not None:
        lines.append(f"• Prezzo in EUR: **€{price_eur:,.4f}**")
    if change_24h is not None:
        lines.append(f"• Variazione 24h: {_format_change(change_24h)}")
    if change_7d is not None:
        lines.append(f"• Variazione 7 giorni: {_format_change(change_7d)}")
    if market_cap is not None:
        lines.append(f"• Market Cap: {_format_number(market_cap)}")
    if volume_24h is not None:
        lines.append(f"• Volume 24h: {_format_number(volume_24h)}")

    # Blocco analisi
    lines.append("\n**⚠️ Contesto:**")
    if ath is not None and ath_change is not None:
        lines.append(f"• ATH (All Time High): ${ath:,.2f} ({ath_change:+.1f}% da ATH)")

    # Sentiment rapido
    if change_24h is not None:
        if change_24h > 5:
            lines.append("• Trend: Forte rialzo nelle ultime 24h 🚀")
        elif change_24h > 0:
            lines.append("• Trend: Leggero rialzo nelle ultime 24h")
        elif change_24h > -5:
            lines.append("• Trend: Leggero ribasso nelle ultime 24h")
        else:
            lines.append("• Trend: Forte ribasso nelle ultime 24h ⚠️")

    lines.append(f"\n📡 Fonte: {source} (aggiornato: {timestamp})")

    return "\n".join(lines)


def _format_stock_response(data: Dict[str, Any]) -> str:
    """
    Formatta risposta azioni in stile Jarvis standardizzato.
    """
    symbol = data.get("symbol", "")
    name = data.get("name", symbol)
    price = data.get("price")
    change = data.get("change")
    change_pct = data.get("change_pct")
    open_price = data.get("open")
    high = data.get("high")
    low = data.get("low")
    volume = data.get("volume")
    source = data.get("source", "Alpha Vantage")
    timestamp = data.get("timestamp", "")

    lines = [f"📊 **{name} ({symbol})** – quotazione live\n"]

    lines.append("**✅ Dati verificati:**")

    if price is not None:
        lines.append(f"• Prezzo attuale: **${price:,.2f}**")
    if change is not None and change_pct is not None:
        emoji = "📈" if change >= 0 else "📉"
        sign = "+" if change >= 0 else ""
        lines.append(f"• Variazione: {emoji} {sign}${change:.2f} ({sign}{change_pct:.2f}%)")
    if open_price is not None:
        lines.append(f"• Apertura: ${open_price:,.2f}")
    if high is not None and low is not None:
        lines.append(f"• Range giornaliero: ${low:,.2f} – ${high:,.2f}")
    if volume is not None:
        lines.append(f"• Volume: {volume:,}")

    lines.append("\n**⚠️ Nota:**")
    lines.append("• I dati sono indicativi e potrebbero avere un ritardo di 15-20 minuti")

    lines.append(f"\n📡 Fonte: {source} (aggiornato: {timestamp})")

    return "\n".join(lines)


def _format_forex_response(data: Dict[str, Any], pair_name: str = "") -> str:
    """
    Formatta risposta forex in stile Jarvis standardizzato.
    """
    pair = data.get("pair", "")
    rate = data.get("rate")
    bid = data.get("bid")
    ask = data.get("ask")
    source = data.get("source", "Alpha Vantage")
    timestamp = data.get("timestamp", "")

    title = pair_name if pair_name else pair
    lines = [f"💱 **{title}** – tasso di cambio live\n"]

    lines.append("**✅ Dati verificati:**")

    if rate is not None:
        lines.append(f"• Tasso attuale: **{rate:.5f}**")
    if bid is not None and ask is not None and bid != ask:
        lines.append(f"• Bid/Ask: {bid:.5f} / {ask:.5f}")
        spread = (ask - bid) * 10000  # pips
        lines.append(f"• Spread: {spread:.1f} pips")

    lines.append("\n**⚠️ Nota:**")
    lines.append("• I tassi forex variano continuamente durante le sessioni di trading")

    lines.append(f"\n📡 Fonte: {source} (aggiornato: {timestamp})")

    return "\n".join(lines)


# ===================== QUERY EXTRACTION =====================


def extract_asset_from_query(query: str) -> Optional[Dict[str, Any]]:
    """
    Estrae l'asset dalla query.
    Ritorna un dict con 'type' (crypto/stock/forex) e info necessarie.
    """
    q = query.lower().strip()

    # Rimuovi parole comuni
    q_clean = re.sub(
        r"\b(prezzo|quotazione|quanto vale|valore|price|quote|ora|oggi|adesso|attuale|"
        r"del|della|di|il|la|lo|un|una|market cap)\b",
        " ",
        q,
    )
    q_clean = re.sub(r"\s+", " ", q_clean).strip()

    # 1. Check forex/commodities first (più specifici)
    for alias, (from_curr, to_curr, name) in FOREX_ALIASES.items():
        if alias in q:
            return {
                "type": "forex",
                "from": from_curr,
                "to": to_curr,
                "name": name,
            }

    # 2. Check crypto
    for alias, coin_id in CRYPTO_ALIASES.items():
        if alias in q or alias in q_clean:
            return {
                "type": "crypto",
                "id": coin_id,
                "alias": alias,
            }

    # 3. Check stocks/indices
    for alias, (symbol, name) in STOCK_ALIASES.items():
        if alias in q or alias in q_clean:
            return {
                "type": "stock",
                "symbol": symbol,
                "name": name,
            }

    # 4. Fallback: prova a interpretare come ticker diretto
    # Se c'è una parola di 2-5 lettere maiuscole, potrebbe essere un ticker
    ticker_match = re.search(r"\b([A-Z]{2,5})\b", query)
    if ticker_match:
        ticker = ticker_match.group(1)
        # Priorità crypto se sembra crypto (usa chiavi da CRYPTO_ALIASES)
        known_crypto_tickers = {k.upper() for k in CRYPTO_ALIASES.keys() if len(k) <= 5}
        if ticker.upper() in known_crypto_tickers:
            crypto_id = CRYPTO_ALIASES.get(ticker.lower())
            if crypto_id:
                return {"type": "crypto", "id": crypto_id, "alias": ticker}
        # Altrimenti prova come stock
        return {"type": "stock", "symbol": ticker, "name": ticker}

    return None


def is_price_query(query: str) -> bool:
    """
    Determina se la query è una richiesta di prezzo/quotazione.
    """
    q = query.lower().strip()

    # Keywords esplicite
    price_keywords = [
        "prezzo",
        "quotazione",
        "quanto vale",
        "valore",
        "price",
        "quote",
        "market cap",
        "capitalizzazione",
        "tasso",
        "cambio",
    ]

    # Check keywords
    has_price_keyword = any(kw in q for kw in price_keywords)

    # Check se contiene un asset noto
    has_asset = extract_asset_from_query(query) is not None

    # È una price query se ha keyword + asset, oppure solo asset con contesto implicito
    if has_price_keyword and has_asset:
        return True

    # Query tipo "btc ora" o "bitcoin oggi" sono anche price query
    if has_asset:
        time_indicators = ["ora", "oggi", "adesso", "now", "live", "attuale", "corrente"]
        if any(t in q for t in time_indicators):
            return True

    return has_price_keyword and has_asset


# ===================== PUBLIC API =====================


async def get_price_answer(query: str) -> Optional[str]:
    """
    API principale: data una query, restituisce la risposta prezzo formattata.

    Args:
        query: Query utente (es. "prezzo bitcoin", "quanto vale ethereum")

    Returns:
        Stringa formattata con i dati di prezzo o messaggio di errore.
    """
    asset = extract_asset_from_query(query)

    if not asset:
        return "❌ Non ho riconosciuto l'asset. Prova con: `prezzo bitcoin`, `quotazione AAPL`, `EUR/USD oggi`"

    asset_type = asset.get("type")

    try:
        if asset_type == "crypto":
            coin_id = asset.get("id")
            data = await _fetch_crypto_price(coin_id)
            if data:
                return _format_crypto_response(data)
            else:
                # Fallback: prova a recuperare dati dalla cache o fornisci info utili
                fallback_msg = await _get_fallback_crypto_info(coin_id, asset.get("alias", coin_id))
                return fallback_msg

        elif asset_type == "stock":
            symbol = asset.get("symbol")
            data = await _fetch_stock_price(symbol)
            if data:
                return _format_stock_response(data)
            else:
                # Fallback con info utili
                return _get_fallback_stock_info(symbol, asset.get("name", symbol))

        elif asset_type == "forex":
            from_curr = asset.get("from")
            to_curr = asset.get("to")
            pair_name = asset.get("name", f"{from_curr}/{to_curr}")
            data = await _fetch_forex_rate(from_curr, to_curr)
            if data:
                return _format_forex_response(data, pair_name)
            else:
                return _get_fallback_forex_info(from_curr, to_curr, pair_name)

    except Exception as e:
        log.error(f"Price agent error: {e}")
        return f"⚠️ Errore nel recupero del prezzo: {e}\n\nProva più tardi o consulta direttamente CoinGecko/TradingView."

    return None


async def _get_fallback_crypto_info(coin_id: str, alias: str) -> str:
    """Fallback per crypto quando l'API fallisce."""
    lines = [f"⚠️ **Prezzo {alias.upper()} non disponibile al momento**\n"]
    lines.append("L'API CoinGecko potrebbe essere in rate limit o non raggiungibile.\n")
    lines.append("**🔗 Consulta direttamente:**")
    lines.append(f"• CoinGecko: https://www.coingecko.com/en/coins/{coin_id}")
    lines.append(f"• CoinMarketCap: https://coinmarketcap.com/currencies/{coin_id}/")
    lines.append(f"• TradingView: https://www.tradingview.com/symbols/{alias.upper()}USD/")
    lines.append(f"\n📡 Riprova tra qualche minuto per dati aggiornati.")
    return "\n".join(lines)


def _get_fallback_stock_info(symbol: str, name: str) -> str:
    """Fallback per azioni quando l'API fallisce."""
    lines = [f"⚠️ **Quotazione {symbol} non disponibile al momento**\n"]
    lines.append("L'API Alpha Vantage potrebbe essere in rate limit (5 chiamate/minuto per free tier).\n")
    lines.append("**🔗 Consulta direttamente:**")
    lines.append(f"• Yahoo Finance: https://finance.yahoo.com/quote/{symbol}")
    lines.append(f"• TradingView: https://www.tradingview.com/symbols/{symbol}/")
    lines.append(f"• Google: https://www.google.com/finance/quote/{symbol}:NASDAQ")
    lines.append(f"\n💡 Suggerimento: configura una API key Alpha Vantage per più chiamate.")
    return "\n".join(lines)


def _get_fallback_forex_info(from_curr: str, to_curr: str, pair_name: str) -> str:
    """Fallback per forex quando l'API fallisce."""
    lines = [f"⚠️ **Tasso {pair_name} non disponibile al momento**\n"]
    lines.append("L'API potrebbe essere in rate limit.\n")
    lines.append("**🔗 Consulta direttamente:**")
    lines.append(f"• Investing.com: https://www.investing.com/currencies/{from_curr.lower()}-{to_curr.lower()}")
    lines.append(f"• TradingView: https://www.tradingview.com/symbols/{from_curr}{to_curr}/")
    lines.append(f"• XE.com: https://www.xe.com/currencyconverter/convert/?From={from_curr}&To={to_curr}")
    return "\n".join(lines)


async def get_price_for_query(query: str) -> Optional[str]:
    """
    Wrapper: verifica se è una price query e restituisce la risposta.
    Ritorna None se non è una query di prezzo valida.
    """
    if not is_price_query(query):
        return None

    return await get_price_answer(query)
