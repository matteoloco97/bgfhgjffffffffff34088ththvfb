import os
import subprocess
import logging
from telegram import Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv

# === LOAD ENV ===
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_ADMIN_ID"))
VENV_PYTHON = "/root/quantumdev-open/venv/bin/python3"
PROJECT_ROOT = "/root/quantumdev-open"

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# === Comandi supportati ===
AGENTI_DISPONIBILI = {
    "backup": "agents/backup.py",
    "flush": "agents/flush_cache.py",
    "restore": "agents/restore.py",
    "monitor": "agents/monitor.py",
    "bootstrapper": "agents/bootstrapper.py"
}

print("✅ AGENTI DISPONIBILI:", AGENTI_DISPONIBILI)

# === /run <nome_task> ===
async def run(update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return

    if len(context.args) == 0:
        await update.message.reply_text("❗ Specifica un task da eseguire (es. /run backup)")
        return

    task = context.args[0].lower()
    script_rel_path = AGENTI_DISPONIBILI.get(task)

    if not script_rel_path:
        await update.message.reply_text(f"❌ Task sconosciuto: {task}")
        return

    script_abs_path = os.path.join(PROJECT_ROOT, script_rel_path)

    try:
        logging.info(f"🔁 Avvio: {VENV_PYTHON} {script_abs_path}")
        subprocess.Popen(
            [VENV_PYTHON, script_abs_path],
            cwd=PROJECT_ROOT,
            env=os.environ.copy()
        )
        await update.message.reply_text(f"🚀 Task '{task}' avviato.")
        logging.info(f"🚀 Task '{task}' avviato via orchestrator.")
    except Exception as e:
        logging.error(f"❌ Errore avvio {task}: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")

# === MAIN ===
if __name__ == "__main__":
    logging.info("🤖 Avvio Orchestrator Agent...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("run", run))
    app.run_polling()
