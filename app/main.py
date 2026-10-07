from contextlib import asynccontextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.api.sources import router, source_info
from app.config import get_settings
from app.db import SessionLocal, engine, initialize_database
from app.models.sources import Source
from app.services.monitor import Monitor, MonitorBusy


def create_app(settings=None, target_engine=None, sessions=None, client=None):
    settings = settings or get_settings()
    target_engine = target_engine or engine
    sessions = sessions or SessionLocal

    @asynccontextmanager
    async def lifespan(app):
        initialize_database(target_engine)
        monitor = Monitor(sessions, settings, client)
        monitor.initialize()
        app.state.monitor = monitor
        monitor.start()
        try:
            yield
        finally:
            await monitor.stop()
            target_engine.dispose()

    application = FastAPI(title="Reporte de Lluvias e Inundaciones", lifespan=lifespan)
    application.state.settings = settings
    application.state.sessions = sessions
    app_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=app_dir / "templates")

    def local_time(value):
        if value is None:
            return "Sin registro"
        value = value.astimezone(ZoneInfo(settings.app_timezone))
        month = "ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC".split()[value.month - 1]
        return f"{value.day:02d} {month} {value.year} - {value:%H:%M} h"

    templates.env.filters["local_time"] = local_time
    application.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
    application.include_router(router)

    @application.get("/health")
    def health():
        return {"status": "ok", "service": "reporte-lluvias-inundaciones"}

    @application.get("/")
    def index(request: Request):
        with sessions() as session:
            sources = [source_info(session, source, settings)
                       for source in session.scalars(select(Source).order_by(Source.id))]
        return templates.TemplateResponse(request=request, name="index.html",
            context={"sources": sources, "timezone": settings.app_timezone})

    @application.post("/sources/check")
    async def check_from_page(request: Request):
        try:
            await request.app.state.monitor.check()
            message = "completed"
        except MonitorBusy:
            message = "busy"
        return RedirectResponse(f"/?check={message}", status_code=303)

    return application


app = create_app()
