import time

from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from src.logging_utils import (
    StructuredLogger,
    generate_request_id,
    get_logs_by_request_id,
)
from src.metrics import (
    cache_saves_total,
    cache_searches_total,
    cache_size_items,
    http_request_duration_seconds,
    http_requests_total,
)
from src.models.schemas import (
    CachedResult,
    SaveRequest,
    SaveResponse,
    SearchRequest,
    SearchResponse,
    TutoringRequest,
    TutoringResponse,
)

app = FastAPI(title="Math Tutor Cache Service (Stub)")
logger = StructuredLogger("cache")

# Initialize cache size to 0 (stub mode)
cache_size_items.set(0)


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Middleware to log all HTTP requests and responses, and record metrics"""
    incoming_request_id = request.headers.get("X-Request-ID")
    request_id = incoming_request_id if incoming_request_id else generate_request_id()
    start_time = time.time()

    # Skip logging /metrics endpoint unless there's an error
    is_metrics_endpoint = request.url.path == "/metrics"

    # Log incoming request (skip /metrics)
    if not is_metrics_endpoint:
        logger.info(
            "Incoming request",
            context={
                "endpoint": request.url.path,
                "method": request.method,
                "client": request.client.host if request.client else "unknown",
            },
            request_id=request_id,
        )

    # Store request_id in request state for access in handlers
    request.state.request_id = request_id

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Record metrics (skip /metrics endpoint to avoid recursion)
        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="cache",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="cache",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

        # Log response (skip /metrics if status is 200)
        if not (is_metrics_endpoint and response.status_code == 200):
            logger.info(
                "Request completed",
                context={
                    "endpoint": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_seconds": round(duration, 3),
                },
                request_id=request_id,
            )

        # Add request_id to response headers
        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as e:
        duration = time.time() - start_time

        # Record error metrics
        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="cache",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="cache",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

        # Always log errors, even for /metrics
        logger.error(
            "Request failed",
            context={
                "endpoint": request.url.path,
                "method": request.method,
                "error": str(e),
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        raise


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "cache",
        "mode": "stub",
        "message": "Cache service running in stub mode - returns dummy data",
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/logs/{request_id}")
async def get_logs(request_id: str):
    """Get logs for a specific request ID"""
    logs = get_logs_by_request_id(request_id)
    return {"request_id": request_id, "logs": logs, "count": len(logs)}


@app.post("/search", response_model=SearchResponse)
async def search_similar(request: SearchRequest, fastapi_request: FastAPIRequest):
    """
    Search for similar Q&A pairs in cache (STUB).

    This is a stub implementation that returns dummy similar questions.
    In the full implementation, this will perform cosine similarity search
    on the vector database.

    Args:
        request: SearchRequest with embedding vector and top_k

    Returns:
        SearchResponse with dummy similar Q&A pairs
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    logger.info(
        "Cache search request received",
        context={
            "embedding_dimensions": len(request.embedding),
            "top_k": request.top_k,
            "mode": "stub",
        },
        request_id=request_id,
    )

    # Record cache search metric
    cache_searches_total.inc()

    # Stub: Return empty results until real vector database is implemented
    results: list[CachedResult] = []

    logger.info(
        "Cache search completed (stub mode - empty results)",
        context={
            "results_count": 0,
            "top_k_requested": request.top_k,
        },
        request_id=request_id,
    )

    return SearchResponse(results=results, count=len(results))


@app.post("/save", response_model=SaveResponse)
async def save_answer(request: SaveRequest, fastapi_request: FastAPIRequest):
    """
    Save Q&A pair to cache (STUB).

    This is a stub implementation that acknowledges the save request
    but doesn't actually store anything. In the full implementation,
    this will save to a vector database.

    Args:
        request: SaveRequest with question, answer, and embedding

    Returns:
        SaveResponse acknowledging the save (but not actually saving)
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    logger.info(
        "Cache save request received",
        context={
            "question_length": len(request.question),
            "answer_length": len(request.answer),
            "embedding_dimensions": len(request.embedding),
            "mode": "stub",
        },
        request_id=request_id,
    )

    # Record cache save metric
    cache_saves_total.inc()

    logger.info(
        "Cache save completed (stub mode - not actually stored)",
        context={
            "question_preview": request.question[:50],
            "answer_preview": request.answer[:50],
        },
        request_id=request_id,
    )

    return SaveResponse(
        status="success",
        message=f"Answer saved (stub mode - not actually stored). Question length: {len(request.question)} chars, Embedding dimensions: {len(request.embedding)}",
    )


@app.post("/tutoring", response_model=TutoringResponse)
async def check_tutoring_cache(
    request: TutoringRequest, fastapi_request: FastAPIRequest
):
    """
    Check tutoring cache for question (STUB - Phase 3).

    This is a stub implementation for Phase 3 tutoring cache.
    Always returns not found. Full implementation planned for later.

    Args:
        request: TutoringRequest with question

    Returns:
        TutoringResponse indicating no data found
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    logger.info(
        "Tutoring cache check request received",
        context={
            "question_length": len(request.question),
            "question_preview": request.question[:50],
            "mode": "stub",
        },
        request_id=request_id,
    )

    logger.info(
        "Tutoring cache check completed - not found (stub mode)",
        context={"found": False},
        request_id=request_id,
    )

    return TutoringResponse(
        found=False,
        data=None,
    )
