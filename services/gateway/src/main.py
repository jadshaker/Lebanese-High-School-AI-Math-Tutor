import json
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from src.config import Config
from src.models.schemas import (
    ChatCompletionChoice,
    ChatCompletionMessageResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Model,
    ModelListResponse,
)

app = FastAPI(title="Math Tutor API Gateway")


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


async def call_data_processing(input_data: str, input_type: str) -> dict:
    """Call the Data Processing service (Phase 1 orchestrator)"""
    url = f"{Config.SERVICES.DATA_PROCESSING_URL}/process-query"
    data = {"input": input_data, "type": input_type}

    req = Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result
    except HTTPError as e:
        error_detail = f"Data Processing service error: {e.code}"
        if e.code == 400:
            error_detail = "Invalid input format"
        raise HTTPException(status_code=502, detail=error_detail)
    except URLError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Data Processing service unavailable: {str(e.reason)}",
        )


async def call_answer_retrieval(query: str) -> dict:
    """Call the Answer Retrieval service (Phase 2 orchestrator)"""
    url = f"{Config.SERVICES.ANSWER_RETRIEVAL_URL}/retrieve-answer"
    data = {"query": query}

    req = Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result
    except HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Answer Retrieval service error: {e.code}",
        )
    except URLError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Answer Retrieval service unavailable: {str(e.reason)}",
        )


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
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
    try:
        # Extract last user message from messages array
        user_message = next(
            (msg.content for msg in reversed(request.messages) if msg.role == "user"),
            None,
        )

        if not user_message:
            raise HTTPException(
                status_code=400,
                detail="No user message found in request",
            )

        # Phase 1: Data Processing (Input → Reformulated Query)
        processing_result = await call_data_processing(user_message, "text")

        # Phase 2: Answer Retrieval (Reformulated Query → Answer)
        retrieval_result = await call_answer_retrieval(
            processing_result["reformulated_query"]
        )

        # Build OpenAI-compatible response
        answer = retrieval_result["answer"]

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
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected response format from service: missing key {str(e)}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
