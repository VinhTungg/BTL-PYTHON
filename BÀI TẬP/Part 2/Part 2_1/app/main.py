from fastapi import FastAPI
from contextlib import asynccontextmanager
import aiosqlite

from .routers.players import router as players_router
from .db.sqlite import ensure_source_table, create_indexes, close_db
from .core.config import DB_FILE


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with aiosqlite.connect(str(DB_FILE)) as conn:
        conn.row_factory = aiosqlite.Row
        await ensure_source_table(conn)
        await create_indexes(conn)
        print(f"Kết nối database đã sẵn sàng: {DB_FILE}")
    
    yield
    
    await close_db()
    print("Đã đóng kết nối database")


app = FastAPI(
    title="Premier League Stats API",
    version="1.0.0",
    description="API để truy vấn thống kê cầu thủ Premier League 2024-2025",
    lifespan=lifespan
)

app.include_router(players_router)