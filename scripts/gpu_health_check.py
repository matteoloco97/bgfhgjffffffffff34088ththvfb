import requests
import os
from dotenv import load_dotenv

load_dotenv()

LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "http://localhost:8000/v1")
MODEL_NAME = os.getenv("LLM_MODEL", "qwen-7b")

def check_gpu_health():
    try:
        # === TEST 1: /chat ===
        chat_resp = requests.post(f"{LLM_ENDPOINT}/chat", json={"message": "ping"})
        if chat_resp.status_code == 200 and chat_resp.json().get("pong") is True:
            print("✅ /chat OK")
        else:
            print("❌ /chat FAILED", chat_resp.text)

        # === TEST 2: /generate ===
        generate_payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": "Sei una GPT neutra e modulare."},
                {"role": "user", "content": "Sei attiva?"}
            ],
            "temperature": 0.7,
            "max_tokens": 100
        }

        gen_resp = requests.post(f"{LLM_ENDPOINT}/chat/completions", json=generate_payload)
        if gen_resp.status_code == 200:
            print("✅ /generate OK")
            print("🔁 Risposta:", gen_resp.json()["choices"][0]["message"]["content"])
        else:
            print("❌ /generate FAILED", gen_resp.text)

    except Exception as e:
        print("🚨 Errore di connessione:", str(e))

if __name__ == "__main__":
    check_gpu_health()
