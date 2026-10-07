from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.db import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verifica que el almacenamiento configurado sea accesible; aún no hay tablas.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    yield
    engine.dispose()


app = FastAPI(title="Reporte de Lluvias e Inundaciones", lifespan=lifespan)
app_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=app_dir / "templates")
app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "reporte-lluvias-inundaciones"}


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")
