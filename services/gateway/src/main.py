import json
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from src.config import Config
from src.models.schemas import (
    FinalResponse,
    QueryRequest,
)

app = FastAPI(title="Math Tutor API Gateway")

# Initialize LangChain LLMs
large_llm = (
    ChatOpenAI(
        model=Config.LLM.LARGE_MODEL,
        temperature=Config.LLM.TEMPERATURE,
        max_completion_tokens=Config.LLM.MAX_TOKENS,
        api_key=SecretStr(Config.API_KEYS.OPENAI),
    )
    if Config.API_KEYS.OPENAI
    else None
)

small_llm = ChatOllama(
    model=Config.OLLAMA.MODEL_NAME,
    base_url=Config.OLLAMA.SERVICE_URL,
)


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
    """Health check endpoint - checks LangChain LLMs and other services"""
    # Check LangChain LLM configurations
    langchain_health = {
        "large_llm": {
            "status": "healthy" if large_llm else "not_configured",
            "provider": "OpenAI via LangChain",
            "model": Config.LLM.LARGE_MODEL if large_llm else None,
        },
        "small_llm": {
            "status": "healthy",
            "provider": "Ollama via LangChain",
            "model": Config.OLLAMA.MODEL_NAME,
            "base_url": Config.OLLAMA.SERVICE_URL,
        },
    }

    # Check embedding service (still REST API based)
    embedding_health = check_service_health("embedding", Config.SERVICES.EMBEDDING_URL)

    all_healthy = (
        langchain_health["large_llm"]["status"] != "not_configured"
        and embedding_health["status"] == "healthy"
    )

    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": "gateway",
        "langchain_llms": langchain_health,
        "services": {"embedding": embedding_health},
    }


async def call_large_llm(query: str) -> dict:
    """Call the large LLM using LangChain to generate an answer"""
    if not large_llm:
        raise HTTPException(
            status_code=503,
            detail="Large LLM not configured: OpenAI API key missing",
        )

    try:
        # Build system prompt for math tutoring
        system_prompt = "You are an expert mathematics tutor for Lebanese high school students. Provide clear, accurate, and educational answers to math questions."

        # Use LangChain to invoke the model
        messages = [
            ("system", system_prompt),
            ("user", query),
        ]
        response = await large_llm.ainvoke(messages)

        return {
            "answer": response.content,
            "model_used": Config.LLM.LARGE_MODEL,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Large LLM error: {str(e)}",
        )


async def call_small_llm(query: str) -> dict:
    """Call the small LLM using LangChain (Ollama) to generate an answer"""
    try:
        # Use LangChain to invoke Ollama model
        response = await small_llm.ainvoke(query)

        return {
            "answer": response.content,
            "model_used": Config.OLLAMA.MODEL_NAME,
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Small LLM error: {str(e)}",
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
