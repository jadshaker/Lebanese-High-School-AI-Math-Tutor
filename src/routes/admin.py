from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.logging_utils import StructuredLogger, get_logs_by_request_id
from src.services.session import service as session_service
from src.services.vector_cache import service as vector_cache

router = APIRouter()
logger = StructuredLogger("gateway")


@router.get("/health")
async def health():
    """Health check — no more inter-service HTTP calls."""
    qdrant_health = await vector_cache.get_health()
    session_count = session_service.get_active_session_count()

    qdrant_ok = qdrant_health.get("qdrant_connected", False)
    status = "healthy" if qdrant_ok else "degraded"

    return {
        "status": status,
        "service": "app",
        "components": {
            "qdrant": qdrant_health,
            "session": {
                "active_sessions": session_count,
                "uptime_seconds": round(session_service.get_uptime(), 1),
            },
        },
    }


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/logs/{request_id}")
async def get_logs(request_id: str):
    """Get logs filtered by request ID"""
    logs = get_logs_by_request_id(request_id)
    return {"request_id": request_id, "logs": logs, "log_count": len(logs)}


@router.get("/track/{request_id}")
async def track_request(request_id: str):
    """Track a request by its ID. Now simple since all logs are in one process."""
    logs = get_logs_by_request_id(request_id)
    return {
        "request_id": request_id,
        "services": {
            "app": {
                "log_count": len(logs),
                "logs": logs,
            }
        },
        "timeline": [{"service": "app", "log": log} for log in logs],
    }
