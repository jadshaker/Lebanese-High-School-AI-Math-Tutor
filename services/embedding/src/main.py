import time

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi import Response
from openai import OpenAI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from src.config import Config
from src.logging_utils import (
    StructuredLogger,
    generate_request_id,
    get_logs_by_request_id,
)
from src.metrics import (
    embedding_dimensions,
    embedding_latency_seconds,
    embedding_requests_total,
    http_request_duration_seconds,
    http_requests_total,
)
from src.models.schemas import EmbedRequest, EmbedResponse

app = FastAPI(title="Math Tutor API Embedding Service")
logger = StructuredLogger("embedding")

# Initialize OpenAI client
client = OpenAI(api_key=Config.API_KEYS.OPENAI) if Config.API_KEYS.OPENAI else None

# Set embedding dimensions gauge
embedding_dimensions.set(Config.EMBEDDING.DIMENSIONS)


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Middleware to log all HTTP requests and responses, and record metrics"""
    request_id = generate_request_id()
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
                service="embedding",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="embedding",
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
                service="embedding",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="embedding",
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
    api_configured = Config.API_KEYS.OPENAI is not None
    return {
        "status": "healthy",
        "service": "embedding",
        "model": Config.EMBEDDING.MODEL,
        "dimensions": Config.EMBEDDING.DIMENSIONS,
        "api_configured": api_configured,
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


@app.post("/embed", response_model=EmbedResponse)
async def embed_text(request: EmbedRequest, fastapi_request: FastAPIRequest):
    """
    Generate embedding for input text using OpenAI's embedding API.
    Falls back to dummy response if API key is not configured.
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    logger.info(
        "Embedding request received",
        context={
            "text_length": len(request.text),
            "model": Config.EMBEDDING.MODEL,
            "dimensions": Config.EMBEDDING.DIMENSIONS,
        },
        request_id=request_id,
    )

    if not client:
        # Fallback to dummy response if no API key
        logger.warning(
            "Using dummy embedding - no API key configured",
            context={"dimensions": Config.EMBEDDING.DIMENSIONS},
            request_id=request_id,
        )
        dummy_embedding = [0.0] * Config.EMBEDDING.DIMENSIONS
        return EmbedResponse(
            embedding=dummy_embedding,
            model="dummy-fallback",
            dimensions=Config.EMBEDDING.DIMENSIONS,
        )

    try:
        logger.info(
            "Calling OpenAI Embeddings API",
            context={
                "model": Config.EMBEDDING.MODEL,
                "input_length": len(request.text),
            },
            request_id=request_id,
        )

        # Record embedding request
        embedding_requests_total.labels(model=Config.EMBEDDING.MODEL).inc()

        # Call OpenAI Embeddings API and measure latency
        api_start = time.time()
        response = client.embeddings.create(
            model=Config.EMBEDDING.MODEL,
            input=request.text,
            dimensions=Config.EMBEDDING.DIMENSIONS,
        )
        api_duration = time.time() - api_start

        # Record latency
        embedding_latency_seconds.labels(model=Config.EMBEDDING.MODEL).observe(
            api_duration
        )

        embedding = response.data[0].embedding
        model_used = response.model

        logger.info(
            "Embedding generated successfully",
            context={
                "model": model_used,
                "dimensions": len(embedding),
                "text_preview": request.text[:50],
                "api_latency_seconds": round(api_duration, 3),
            },
            request_id=request_id,
        )

        return EmbedResponse(
            embedding=embedding,
            model=model_used,
            dimensions=len(embedding),
        )

    except Exception as e:
        logger.error(
            "OpenAI Embeddings API error",
            context={
                "error": str(e),
                "error_type": type(e).__name__,
                "model": Config.EMBEDDING.MODEL,
            },
            request_id=request_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"OpenAI Embeddings API error: {str(e)}",
        )
