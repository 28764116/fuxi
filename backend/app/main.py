import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.init_db import init_db
from memory.router import router as memory_router, ws_router as memory_ws_router
from simulation.router import router as simulation_router
from graph.router import router as graph_router

logger = logging.getLogger("fuxi")

OPENING_VERSE = """
┌─────────────────────────────────────┐

一画伏羲开天地，
  两辨阴阳悟玄机。
  五行流转藏真意，
  万象森罗纳掌中。
  千秋变数皆有数，
  百代兴衰尽可通。
  九宫凝神观云变，
  数策知机定太平。
└─────────────────────────────────────┘
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(OPENING_VERSE)
    print(OPENING_VERSE)
    await init_db()
    logger.info("Database tables initialized.")
    yield


app = FastAPI(title="Fuxi Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memory_router, prefix="/api")
app.include_router(memory_ws_router, prefix="/api")  # WebSocket routes without auth
app.include_router(simulation_router, prefix="/api")
app.include_router(graph_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/health")
async def api_health():
    return {"status": "ok"}
