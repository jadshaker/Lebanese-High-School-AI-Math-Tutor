import time
import uuid

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
    http_request_duration_seconds,
    http_requests_total,
    llm_latency_seconds,
    llm_requests_total,
    llm_tokens_total,
)
from src.models.schemas import (
    ChatCompletionChoice,
    ChatCompletionMessageResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
)

app = FastAPI(title="Math Tutor API Large LLM Service")
logger = StructuredLogger("large_llm")

# Initialize OpenAI client
client = (
    OpenAI(api_key=Config.API_KEYS.OPENAI, timeout=Config.LARGE_LLM_TIMEOUT)
    if Config.API_KEYS.OPENAI
    else None
)


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
                service="large_llm",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="large_llm",
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
                service="large_llm",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="large_llm",
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
        "service": "large_llm",
        "model": Config.LARGE_LLM_MODEL_NAME,
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


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(request: ChatCompletionRequest, fastapi_request: FastAPIRequest):
    """
    OpenAI-compatible chat completions endpoint.
    Generates answers using OpenAI's GPT-4 API.
    Falls back to dummy response if API key is not configured.
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    # Log incoming chat completion request
    logger.info(
        "Processing chat completion",
        context={
            "model": request.model,
            "message_count": len(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "api_configured": client is not None,
        },
        request_id=request_id,
    )

    if not client:
        # Fallback to dummy response if no API key
        logger.warning(
            "API key not configured, returning dummy response",
            context={},
            request_id=request_id,
        )

        last_user_message = next(
            (msg.content for msg in reversed(request.messages) if msg.role == "user"),
            "No user message",
        )
        dummy_answer = (
            f"[Dummy Response] API key not configured. Query: {last_user_message}"
        )

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model="dummy-fallback",
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionMessageResponse(content=dummy_answer),
                    finish_reason="stop",
                )
            ],
        )

    try:
        logger.info(
            "Calling OpenAI API",
            context={"model": request.model},
            request_id=request_id,
        )

        # Call OpenAI API with the provided messages
        llm_start_time = time.time()
        response = client.chat.completions.create(
            model=request.model,
            messages=[
                {"role": msg.role, "content": msg.content}  # type: ignore[misc]
                for msg in request.messages
            ],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        llm_duration = time.time() - llm_start_time

        answer = response.choices[0].message.content or ""

        # Record LLM metrics
        model_name = response.model
        llm_requests_total.labels(model=model_name).inc()
        llm_latency_seconds.labels(model=model_name).observe(llm_duration)

        # Record token metrics if available
        if response.usage:
            if response.usage.prompt_tokens:
                llm_tokens_total.labels(model=model_name, type="prompt").inc(
                    response.usage.prompt_tokens
                )
            if response.usage.completion_tokens:
                llm_tokens_total.labels(model=model_name, type="completion").inc(
                    response.usage.completion_tokens
                )

        # Log response details
        logger.info(
            "Chat completion successful",
            context={
                "answer_length": len(answer),
                "model": response.model,
                "prompt_tokens": (
                    response.usage.prompt_tokens if response.usage else None
                ),
                "completion_tokens": (
                    response.usage.completion_tokens if response.usage else None
                ),
                "total_tokens": response.usage.total_tokens if response.usage else None,
                "llm_duration_seconds": round(llm_duration, 3),
            },
            request_id=request_id,
        )

        return ChatCompletionResponse(
            id=response.id,
            created=response.created,
            model=response.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionMessageResponse(content=answer),
                    finish_reason="stop",
                )
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Chat completion failed",
            context={
                "error": str(e),
                "error_type": type(e).__name__,
                "model": request.model,
            },
            request_id=request_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"OpenAI API error: {str(e)}",
        )
