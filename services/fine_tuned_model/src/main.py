import json
import time
from urllib.request import Request, urlopen

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
from src.models.schemas import ChatCompletionRequest, ChatCompletionResponse

app = FastAPI(title="Fine-Tuned Model Service", version="1.0.0")
logger = StructuredLogger("fine_tuned_model")

# Initialize OpenAI client pointing to Ollama's OpenAI-compatible endpoint
client = OpenAI(
    base_url=f"{Config.FINE_TUNED_MODEL_SERVICE_URL}/v1",
    api_key="dummy",  # Ollama doesn't require authentication
)


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
                service="fine_tuned_model",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="fine_tuned_model",
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
                service="fine_tuned_model",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="fine_tuned_model",
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
def health_check() -> dict[str, str | bool]:
    """Health check endpoint that verifies Ollama connectivity and model availability."""
    ollama_reachable = False
    model_available = False

    try:
        req = Request(
            f"{Config.FINE_TUNED_MODEL_SERVICE_URL}/api/tags",
            method="GET",
        )

        with urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
            ollama_reachable = True

            models = result.get("models", [])
            model_available = any(
                model.get("name") == Config.FINE_TUNED_MODEL_NAME for model in models
            )

    except Exception:
        pass

    return {
        "status": "healthy" if ollama_reachable and model_available else "degraded",
        "service": "fine_tuned_model",
        "ollama_reachable": ollama_reachable,
        "model_available": model_available,
        "configured_model": Config.FINE_TUNED_MODEL_NAME,
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
def chat_completions(
    request: ChatCompletionRequest, fastapi_request: FastAPIRequest
) -> ChatCompletionResponse:
    """
    OpenAI-compatible chat completions endpoint.
    Forwards requests to Ollama's OpenAI-compatible API.

    Args:
        request: ChatCompletionRequest with messages and model
        fastapi_request: FastAPI request for extracting request_id

    Returns:
        ChatCompletionResponse from Ollama

    Raises:
        HTTPException: If Ollama service is unavailable or returns an error
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    try:
        # Log incoming chat completion request
        model_name = request.model or Config.FINE_TUNED_MODEL_NAME
        logger.info(
            "Processing chat completion",
            context={
                "model": model_name,
                "message_count": len(request.messages),
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            },
            request_id=request_id,
        )

        # Build optional parameters
        extra_params = {}
        if request.temperature is not None:
            extra_params["temperature"] = request.temperature
        if request.max_tokens is not None:
            extra_params["max_tokens"] = request.max_tokens
        if request.stream is not None:
            extra_params["stream"] = request.stream

        logger.info(
            "Calling Ollama via OpenAI SDK",
            context={"model": model_name},
            request_id=request_id,
        )

        # Call Ollama using OpenAI SDK
        llm_start_time = time.time()
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": msg.role, "content": msg.content} for msg in request.messages
            ],
            extra_body={"keep_alive": -1},  # Ollama-specific parameter
            **extra_params,
        )
        llm_duration = time.time() - llm_start_time

        # Record LLM metrics
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
        answer_content = response.choices[0].message.content if response.choices else ""
        logger.info(
            "Chat completion successful",
            context={
                "answer_length": len(answer_content),
                "model": response.model,
                "llm_duration_seconds": round(llm_duration, 3),
            },
            request_id=request_id,
        )

        # Convert to our response model
        return ChatCompletionResponse(**response.model_dump())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Chat completion failed",
            context={
                "error": str(e),
                "error_type": type(e).__name__,
                "model": request.model or Config.FINE_TUNED_MODEL_NAME,
            },
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Fine-tuned model service error: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)
