"""Main FastAPI app for AgentViz."""
import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import STRIPE_SECRET_KEY
from app.database import init_db
from app.routers import auth, dashboard, oauth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AgentViz", version="0.1.0")

templates_dir = Path(__file__).parent / "templates"
app.state.templates = Jinja2Templates(directory=str(templates_dir))

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(oauth.router)


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("AgentViz started")


@app.get("/")
async def landing(request: Request):
    return app.state.templates.TemplateResponse("landing.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok", "service": "AgentViz"}
