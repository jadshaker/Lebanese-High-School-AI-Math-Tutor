import json
import time
import uuid
from typing import Any
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
from src.middleware import logging_and_metrics_middleware
from src.models.schemas import (
    ChatCompletionChoice,
    ChatCompletionMessageResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Model,
    ModelListResponse,
)
from src.orchestrators import process_user_input, retrieve_answer

app = FastAPI(title="Math Tutor API Gateway")
logger = StructuredLogger("gateway")


@app.middleware("http")
async def middleware(request: FastAPIRequest, call_next):
    """Apply logging and metrics middleware"""
    return await logging_and_metrics_middleware(request, call_next)


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
    """Health check endpoint - checks all individual services"""
    services = {
        "input_processor": Config.SERVICES.INPUT_PROCESSOR_URL,
        "reformulator": Config.SERVICES.REFORMULATOR_URL,
        "embedding": Config.SERVICES.EMBEDDING_URL,
        "cache": Config.SERVICES.CACHE_URL,
        "small_llm": Config.SERVICES.SMALL_LLM_URL,
        "large_llm": Config.SERVICES.LARGE_LLM_URL,
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
    # Only query services that have /logs endpoint (Python FastAPI services)
    # Ollama services (small-llm, reformulator, fine-tuned-model) don't have this endpoint
    services_with_logs = {
        "gateway": Config.SERVICES.GATEWAY_URL,
        "input-processor": Config.SERVICES.INPUT_PROCESSOR_URL,
        "embedding": Config.SERVICES.EMBEDDING_URL,
        "cache": Config.SERVICES.CACHE_URL,
        "large-llm": Config.SERVICES.LARGE_LLM_URL,
    }

    trace: dict[str, Any] = {
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
    for service_name, service_url in services_with_logs.items():
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
       - Embedding → Cache → Small LLM → [conditional] Large LLM → Save
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
            "Starting chat completion pipeline",
            context={
                "model": request.model,
                "user_message": user_message[:100],
                "message_count": len(request.messages),
            },
            request_id=request_id,
        )

        pipeline_start = time.time()

        # ===== DATA PROCESSING =====
        processing_result = await process_user_input(user_message, request_id)
        reformulated_query = processing_result["reformulated_query"]

        # ===== ANSWER RETRIEVAL =====
        retrieval_result = await retrieve_answer(reformulated_query, request_id)
        answer = retrieval_result["answer"]
        source = retrieval_result["source"]

        # ===== LATENCY SUMMARY =====
        total_duration = round(time.time() - pipeline_start, 3)
        latency = {
            **processing_result.get("latency", {}),
            **retrieval_result.get("latency", {}),
            "total": total_duration,
        }

        # Log a clear latency breakdown
        breakdown = " | ".join(f"{k}: {v}s" for k, v in latency.items())
        logger.info(
            f"⏱ Latency breakdown: {breakdown}",
            context={"latency": latency},
            request_id=request_id,
        )

        logger.info(
            "Chat completion pipeline successful",
            context={
                "total_answer_length": len(answer),
                "source": source,
                "total_latency_s": total_duration,
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
