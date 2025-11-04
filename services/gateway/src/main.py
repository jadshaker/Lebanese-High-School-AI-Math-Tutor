import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from src.config import Config
from src.models.schemas import (
    FinalResponse,
    QueryRequest,
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
    """Health check endpoint - checks all services"""
    services = {
        "large_llm": Config.SERVICES.LARGE_LLM_URL,
        "small_llm": Config.SERVICES.SMALL_LLM_URL,
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


async def call_large_llm(query: str) -> dict:
    """Call the large LLM service to generate an answer"""
    url = f"{Config.SERVICES.LARGE_LLM_URL}/generate"
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
            detail=f"Large LLM service error: {e.code}",
        )
    except URLError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Large LLM service unavailable: {str(e.reason)}",
        )


async def call_small_llm(query: str) -> dict:
    """Call the small LLM service (Ollama) to generate an answer"""
    url = f"{Config.SERVICES.SMALL_LLM_URL}/query"
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
            detail=f"Small LLM service error: {e.code}",
        )
    except URLError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Small LLM service unavailable: {str(e.reason)}",
        )


@app.post("/query", response_model=FinalResponse)
async def process_query(request: QueryRequest):
    """
    Main query processing endpoint implementing the multi-model architecture:

    By default, routes to small_llm (Ollama on HPC). Set use_large_llm=true to use large LLM.

    Flow:
    1. Check use_large_llm flag
    2. Route to appropriate service:
       - use_large_llm=false (default): use small LLM (Ollama)
       - use_large_llm=true: use large LLM (OpenAI GPT-4)
    3. If small LLM fails, fallback to large LLM
    """
    try:
        if request.use_large_llm:
            llm_response = await call_large_llm(request.query)
            path_taken = "large_llm"
            fallback_used = False
        else:
            try:
                llm_response = await call_small_llm(request.query)
                path_taken = "small_llm"
                fallback_used = False
            except HTTPException:
                llm_response = await call_large_llm(request.query)
                path_taken = "large_llm"
                fallback_used = True

        return FinalResponse(
            answer=llm_response["answer"],
            path_taken=path_taken,
            verified=True,
            fallback_used=fallback_used,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
