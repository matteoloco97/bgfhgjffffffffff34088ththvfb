# core/smart_intent_classifier.py
import re

class SmartIntentClassifier:
    def __init__(self):
        # keyword set per info instabili
        self.weather_kw = {"meteo", "previsioni", "che tempo", "weather", "oggi", "domani"}
        self.price_kw   = {
            "prezzo", "quotazione", "quanto vale", "valore",
            "btc", "bitcoin", "eth", "ethereum", "eurusd", "eur/usd", "cambio", "borsa", "azioni", "indice"
        }
        # note: “oggi” da solo non basta: lo abbiniamo a contesto meteo/prezzi nel check

    def _looks_like_url(self, s: str) -> bool:
        return bool(re.search(r'https?://\S+', s))

    def _looks_like_calc(self, s: str) -> bool:
        # match veloce per espressioni semplici
        return bool(re.fullmatch(r'[0-9\(\)\+\-\*/\.\s\^%]+', s.strip()))

    def classify(self, query: str) -> dict:
        q = (query or "").strip().lower()

        # 1) URL → WEB_READ
        if self._looks_like_url(q):
            m = re.search(r'(https?://\S+)', q)
            return {
                "intent": "WEB_READ",
                "confidence": 1.0,
                "reason": "url_detected",
                "url": m.group(1) if m else None
            }

        # 2) CALCULATOR (formule semplici)
        if self._looks_like_calc(q):
            return {"intent": "CALCULATOR", "confidence": 1.0, "reason": "calculator_fast_path"}

        # 3) Meteo → WEB_SEARCH
        if any(kw in q for kw in self.weather_kw) and ("meteo" in q or "che tempo" in q or "weather" in q):
            return {"intent": "WEB_SEARCH", "confidence": 0.98, "reason": "unstable_info:weather"}

        # 4) Prezzi/quotazioni/crypto/forex/borsa → WEB_SEARCH
        if any(kw in q for kw in self.price_kw):
            return {"intent": "WEB_SEARCH", "confidence": 0.98, "reason": "unstable_info:prices_fx_crypto"}

        # 5) Definizioni/conoscenza stabile → DIRECT_LLM
        return {"intent": "DIRECT_LLM", "confidence": 0.95, "reason": "llm_classified"}
