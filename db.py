import aiomysql
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

_pool = None

async def init_db():
    global _pool
    _pool = await aiomysql.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
        autocommit=False,
        minsize=2,
        maxsize=10,
        charset="utf8mb4"
    )

async def close_db():
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None

def get_pool():
    if _pool is None:
        raise RuntimeError("DB non inizializzato — chiama init_db() prima.")
    return _pool
