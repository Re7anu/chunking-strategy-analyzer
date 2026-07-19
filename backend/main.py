import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.db.db_client import init_db
from src.db.qdrant_client import qdrant_manager
from src.auth.router import router as auth_router
from src.routers.chat import router as chat_router
from src.routers.ingest import router as ingest_router
from src.routers.search import router as search_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize PostgreSQL connection pool and Qdrant collection on startup
    init_db()
    qdrant_manager.init_qdrant()
    yield


app = FastAPI(lifespan=lifespan)

# Note: API routes MUST be registered before mounting StaticFiles at "/" to prevent path collisions.

# Auth — /api/auth/register, /api/auth/login, /api/auth/logout, /api/auth/me
app.include_router(auth_router)

# Chat threads, document library, and streaming chat — /api/threads/*, /api/documents, /api/chat
app.include_router(chat_router)

# Ingestion pipeline — /api/ingest, /api/ingest-pdf
app.include_router(ingest_router)

# Hybrid search and strategy comparison — /api/search, /api/compare
app.include_router(search_router)

# Mount frontend static files directory dynamically using absolute paths
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
