from fastapi import FastAPI

from .routers.players import router as players_router

app = FastAPI(title="Premier League Stats API", version="1.0.0")
app.include_router(players_router)