import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN   = os.getenv("BOT_TOKEN")
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", 3306))
DB_NAME     = os.getenv("DB_NAME")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
GRUPPO_ID = int(os.getenv("GRUPPO_ID", 0))

required = {
    "BOT_TOKEN":   BOT_TOKEN,
    "DB_NAME":     DB_NAME,
    "DB_USER":     DB_USER,
    "DB_PASSWORD": DB_PASSWORD,
}
for nome, valore in required.items():
    if not valore:
        raise EnvironmentError(f"Variabile d'ambiente mancante: {nome}")
