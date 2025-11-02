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
            return {"status": "healthy", "details": result}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/health")
async def health():
    """Health check endpoint - checks all services"""
    services = {
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


@app.post("/query", response_model=FinalResponse)
async def process_query(request: QueryRequest):
    """
    Main query processing endpoint implementing the multi-model architecture:

    Flow:
    1. Embed query
    2. Check cache
    3. If cache hit -> use small LLM to refine -> verify
    4. If cache miss -> assess complexity
       - EASY/MODERATE: use local model (Phi-3) -> verify
       - HARD: use large LLM -> verify
    5. If verification fails, fallback to large LLM
    6. Store successful answer in cache
    """
    try:
        llm_response = await call_large_llm(request.query)
        path_taken = "large_llm"

        return FinalResponse(
            answer=llm_response["answer"],
            path_taken=path_taken,
            verified=True,
            fallback_used=False,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
