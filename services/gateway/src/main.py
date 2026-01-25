import json
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from src.config import Config
from src.logging_utils import (
    StructuredLogger,
    generate_request_id,
    get_logs_by_request_id,
)
from src.metrics import (
    gateway_answer_retrieval_duration_seconds,
    gateway_data_processing_duration_seconds,
    gateway_errors_total,
    http_request_duration_seconds,
    http_requests_total,
)
from src.models.schemas import (
    ChatCompletionChoice,
    ChatCompletionMessageResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Model,
    ModelListResponse,
)

app = FastAPI(title="Math Tutor API Gateway")
logger = StructuredLogger("gateway")


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
                service="gateway",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="gateway",
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
                service="gateway",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="gateway",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

            gateway_errors_total.labels(error_type=type(e).__name__).inc()

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


def check_service_health(service_name: str, service_url: str) -> dict:
    """Check health of a single service"""
    try:
        req = Request(
            f"{service_url}/health",
            method="GET",
        )
        with urlopen(req, timeout=2) as response:
            result = json.loads(response.read().decode("utf-8"))
            service_status = result.get("status", "healthy")
            return {"status": service_status, "details": result}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/health")
async def health():
    """Health check endpoint - checks orchestrator services"""
    services = {
        "data_processing": Config.SERVICES.DATA_PROCESSING_URL,
        "answer_retrieval": Config.SERVICES.ANSWER_RETRIEVAL_URL,
    }

    service_health = {}
    all_healthy = True

    for service_name, service_url in services.items():
        health_status = check_service_health(service_name, service_url)
        service_health[service_name] = health_status
        if health_status["status"] != "healthy":
            all_healthy = False

    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": "gateway",
        "services": service_health,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/track/{request_id}")
async def track_request(request_id: str):
    """
    Track a request across all services by its request ID.

    Returns logs from all services that contain this request ID,
    providing a complete trace of the request's journey through the system.
    """
    all_services = {
        "gateway": Config.SERVICES.GATEWAY_URL,
        "data-processing": Config.SERVICES.DATA_PROCESSING_URL,
        "input-processor": Config.SERVICES.INPUT_PROCESSOR_URL,
        "reformulator": Config.SERVICES.REFORMULATOR_URL,
        "answer-retrieval": Config.SERVICES.ANSWER_RETRIEVAL_URL,
        "embedding": Config.SERVICES.EMBEDDING_URL,
        "cache": Config.SERVICES.CACHE_URL,
        "small-llm": Config.SERVICES.SMALL_LLM_URL,
        "large-llm": Config.SERVICES.LARGE_LLM_URL,
        "fine-tuned-model": Config.SERVICES.FINE_TUNED_MODEL_URL,
    }

    trace = {
        "request_id": request_id,
        "services": {},
        "timeline": [],
    }

    # Get logs from gateway (current service)
    gateway_logs = get_logs_by_request_id(request_id)
    if gateway_logs:
        trace["services"]["gateway"] = {
            "log_count": len(gateway_logs),
            "logs": gateway_logs,
        }
        for log in gateway_logs:
            trace["timeline"].append({"service": "gateway", "log": log})

    # Query each service for logs with this request ID
    for service_name, service_url in all_services.items():
        if service_name == "gateway":
            continue  # Already added above

        try:
            req = Request(
                f"{service_url}/logs/{request_id}",
                method="GET",
            )

            with urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
                logs = result.get("logs", [])

                if logs:
                    trace["services"][service_name] = {
                        "log_count": len(logs),
                        "logs": logs,
                    }

                    for log in logs:
                        trace["timeline"].append({"service": service_name, "log": log})

        except Exception:
            # Service doesn't have the /logs endpoint or is unreachable
            continue

    # Sort timeline chronologically by extracting timestamp from log line
    trace["timeline"].sort(key=lambda x: x["log"][:23])  # Sort by timestamp prefix

    return trace


@app.get("/v1/models", response_model=ModelListResponse)
async def list_models():
    """
    OpenAI-compatible models list endpoint.
    Returns the available model(s) for Open WebUI.
    """
    return ModelListResponse(
        data=[
            Model(
                id="math-tutor",
                created=int(time.time()),
                owned_by="lebanese-high-school-math-tutor",
            )
        ]
    )


async def call_data_processing(
    input_data: str, input_type: str, request_id: str
) -> dict:
    """Call the Data Processing service (Phase 1 orchestrator)"""
    url = f"{Config.SERVICES.DATA_PROCESSING_URL}/process-query"
    data = {"input": input_data, "type": input_type}

    logger.info(
        "Calling Data Processing service",
        context={"url": url, "input_type": input_type},
        request_id=request_id,
    )

    req = Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Request-ID": request_id},
        method="POST",
    )

    # Record timing for data processing
    start_time = time.time()
    try:
        with urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            duration = time.time() - start_time
            gateway_data_processing_duration_seconds.observe(duration)

            logger.info(
                "Data Processing service responded",
                context={
                    "reformulated_query": result.get("reformulated_query", "")[:100],
                    "duration_seconds": round(duration, 3),
                },
                request_id=request_id,
            )
            return result
    except HTTPError as e:
        duration = time.time() - start_time
        gateway_data_processing_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="data_processing_http_error").inc()

        error_detail = f"Data Processing service error: {e.code}"
        if e.code == 400:
            error_detail = "Invalid input format"
        logger.error(
            "Data Processing service HTTP error",
            context={"status_code": e.code, "error": error_detail},
            request_id=request_id,
        )
        raise HTTPException(status_code=502, detail=error_detail)
    except URLError as e:
        duration = time.time() - start_time
        gateway_data_processing_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="data_processing_unavailable").inc()

        logger.error(
            "Data Processing service unavailable",
            context={"error": str(e.reason)},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Data Processing service unavailable: {str(e.reason)}",
        )


async def call_answer_retrieval(query: str, request_id: str) -> dict:
    """Call the Answer Retrieval service (Phase 2 orchestrator)"""
    url = f"{Config.SERVICES.ANSWER_RETRIEVAL_URL}/retrieve-answer"
    data = {"query": query}

    logger.info(
        "Calling Answer Retrieval service",
        context={"url": url, "query": query[:100]},
        request_id=request_id,
    )

    req = Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Request-ID": request_id},
        method="POST",
    )

    # Record timing for answer retrieval
    start_time = time.time()
    try:
        with urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            duration = time.time() - start_time
            gateway_answer_retrieval_duration_seconds.observe(duration)

            logger.info(
                "Answer Retrieval service responded",
                context={
                    "source": result.get("source", "unknown"),
                    "used_cache": result.get("used_cache", False),
                    "duration_seconds": round(duration, 3),
                },
                request_id=request_id,
            )
            return result
    except HTTPError as e:
        duration = time.time() - start_time
        gateway_answer_retrieval_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="answer_retrieval_http_error").inc()

        logger.error(
            "Answer Retrieval service HTTP error",
            context={"status_code": e.code},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Answer Retrieval service error: {e.code}",
        )
    except URLError as e:
        duration = time.time() - start_time
        gateway_answer_retrieval_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="answer_retrieval_unavailable").inc()

        logger.error(
            "Answer Retrieval service unavailable",
            context={"error": str(e.reason)},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Answer Retrieval service unavailable: {str(e.reason)}",
        )


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest, fastapi_request: FastAPIRequest
):
    """
    OpenAI-compatible chat completions endpoint - orchestrates the complete pipeline.

    Flow:
    1. Extract last user message from conversation
    2. Phase 1 (Data Processing): Process and reformulate user input
       - Input Processor → Reformulator
    3. Phase 2 (Answer Retrieval): Get answer using cache and LLMs
       - Embedding → Cache → Small LLM → [conditional] Large LLM
    4. Return answer in OpenAI format

    Returns OpenAI-compatible chat completion response.
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    try:
        # Extract last user message from messages array
        user_message = next(
            (msg.content for msg in reversed(request.messages) if msg.role == "user"),
            None,
        )

        if not user_message:
            logger.warning(
                "No user message in request",
                context={"messages_count": len(request.messages)},
                request_id=request_id,
            )
            raise HTTPException(
                status_code=400,
                detail="No user message found in request",
            )

        logger.info(
            "Processing chat completion",
            context={
                "model": request.model,
                "user_message": user_message[:100],
                "message_count": len(request.messages),
            },
            request_id=request_id,
        )

        # Phase 1: Data Processing (Input → Reformulated Query)
        processing_result = await call_data_processing(user_message, "text", request_id)

        # Phase 2: Answer Retrieval (Reformulated Query → Answer)
        retrieval_result = await call_answer_retrieval(
            processing_result["reformulated_query"], request_id
        )

        # Build OpenAI-compatible response
        answer = retrieval_result["answer"]

        logger.info(
            "Chat completion successful",
            context={
                "answer_length": len(answer),
                "source": retrieval_result.get("source", "unknown"),
            },
            request_id=request_id,
        )

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=request.model,
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
    except KeyError as e:
        logger.error(
            "Unexpected response format",
            context={"missing_key": str(e)},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected response format from service: missing key {str(e)}",
        )
    except Exception as e:
        logger.error(
            "Internal error in chat completion",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
