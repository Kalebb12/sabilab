"""FastAPI server for SabiLab."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import config
from db import init_db
from app.loader import list_scenarios


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on application startup."""
    init_db()
    yield


app = FastAPI(title="SabiLab API", lifespan=lifespan)

# Mount static files directory for client assets
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


@app.get("/scenarios")
def get_scenarios():
    """List all available scenarios from the scenarios directory."""
    return list_scenarios()


@app.get("/health")
def health_check():
    """Return health status of the application."""
    return {"status": "ok"}
