from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.models.sources import Source, SourceCheck, SourceSnapshot
from app.services.monitor import MonitorBusy, current_snapshot, latest_check, status_for

router = APIRouter(prefix="/api/sources", tags=["sources"])


def snapshot_info(snapshot):
    if not snapshot:
        return None
    return {field: getattr(snapshot, field) for field in (
        "id", "fetched_at", "detected_issue_time", "validity_start", "validity_end",
        "content_hash", "content_type", "source_url", "metadata_json")}


def check_info(check):
    return {field: getattr(check, field) for field in (
        "id", "checked_at", "http_status", "success", "error_message", "etag", "last_modified",
        "detected_issue_time", "content_hash", "changed", "snapshot_id")}


def source_info(session, source, settings):
    last = latest_check(session, source.id)
    success = latest_check(session, source.id, successful=True)
    snapshot = current_snapshot(session, source.id)
    return {"key": source.key, "name": source.name, "organization": source.organization,
        "enabled": source.enabled, "is_primary": source.is_primary,
        "last_check": last.checked_at if last else None,
        "last_success": success.checked_at if success else None,
        "latest_snapshot": snapshot_info(snapshot),
        "detected_issue_time": snapshot.detected_issue_time if snapshot else None,
        "status": status_for(session, source, settings),
        "changed_on_last_check": last.changed if last else False}


def require_source(session, key):
    source = session.scalar(select(Source).where(Source.key == key))
    if source is None:
        raise HTTPException(404, "Fuente desconocida")
    return source


@router.get("")
def list_sources(request: Request):
    with request.app.state.sessions() as session:
        return [source_info(session, source, request.app.state.settings)
                for source in session.scalars(select(Source).order_by(Source.id))]


@router.post("/check")
async def check_all(request: Request):
    try:
        return {"checks": await request.app.state.monitor.check()}
    except MonitorBusy:
        raise HTTPException(409, "Ya hay una comprobación en curso")


@router.get("/{source_key}")
def source_detail(source_key: str, request: Request):
    with request.app.state.sessions() as session:
        source = require_source(session, source_key)
        result = source_info(session, source, request.app.state.settings)
        result["checks"] = [check_info(c) for c in session.scalars(select(SourceCheck)
            .where(SourceCheck.source_id == source.id).order_by(SourceCheck.id.desc()).limit(20))]
        result["snapshots"] = [snapshot_info(s) for s in session.scalars(select(SourceSnapshot)
            .where(SourceSnapshot.source_id == source.id).order_by(SourceSnapshot.id.desc()).limit(20))]
        return result


@router.post("/{source_key}/check")
async def check_source(source_key: str, request: Request):
    with request.app.state.sessions() as session:
        source = require_source(session, source_key)
        if not source.enabled:
            raise HTTPException(409, "Fuente deshabilitada")
    try:
        return {"checks": await request.app.state.monitor.check(source_key)}
    except MonitorBusy:
        raise HTTPException(409, "Ya hay una comprobación en curso")


@router.get("/{source_key}/snapshots")
def source_snapshots(source_key: str, request: Request, limit: int = 20, offset: int = 0):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Paginación inválida")
    with request.app.state.sessions() as session:
        source = require_source(session, source_key)
        return [snapshot_info(s) for s in session.scalars(select(SourceSnapshot)
            .where(SourceSnapshot.source_id == source.id).order_by(SourceSnapshot.id.desc()).offset(offset).limit(limit))]
