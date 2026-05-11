import os
import asyncio
import aiomysql
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "sql")

async def get_connection():
    return await aiomysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        autocommit=False
    )

async def get_migrazioni_applicate(cur):
    await cur.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            filename VARCHAR(255) NOT NULL UNIQUE,
            applicata_il DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await cur.execute("SELECT filename FROM migrations ORDER BY filename")
    righe = await cur.fetchall()
    return {r[0] for r in righe}

async def esegui_migrazioni():
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            applicate = await get_migrazioni_applicate(cur)
            await conn.commit()

            files = sorted([
                f for f in os.listdir(MIGRATIONS_DIR)
                if f.endswith(".sql")
            ])

            nuove = [f for f in files if f not in applicate]

            if not nuove:
                print("Nessuna nuova migrazione da applicare.")
                return

            for filename in nuove:
                filepath = os.path.join(MIGRATIONS_DIR, filename)
                print(f"Applico: {filename}")

                with open(filepath, "r", encoding="utf-8") as f:
                    sql = f.read()

                try:
                    for statement in sql.split(";"):
                        statement = statement.strip()
                        if statement:
                            await cur.execute(statement)

                    await cur.execute(
                        "INSERT INTO migrations (filename) VALUES (%s)",
                        (filename,)
                    )
                    await conn.commit()
                    print(f"OK: {filename}")

                except Exception as e:
                    await conn.rollback()
                    print(f"ERRORE in {filename}: {e}")
                    print("Rollback eseguito. Migrazioni successive non applicate.")
                    break
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(esegui_migrazioni())
