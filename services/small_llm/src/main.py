import json
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from openai import OpenAI
from src.config import Config
from src.models.schemas import QueryRequest, QueryResponse

app = FastAPI(title="Small LLM Service", version="1.0.0")

client = OpenAI(
    base_url=f"{Config.SMALL_LLM_SERVICE_URL}/v1",
    api_key="ollama",
)


@app.get("/health")
def health_check() -> dict[str, str | bool]:
    """Health check endpoint that verifies Ollama connectivity and model availability."""
    ollama_reachable = False
    model_available = False

    try:
        req = Request(
            f"{Config.SMALL_LLM_SERVICE_URL}/api/tags",
            method="GET",
        )

        with urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
            ollama_reachable = True

            models = result.get("models", [])
            model_available = any(
                model.get("name") == Config.SMALL_LLM_MODEL_NAME for model in models
            )

    except Exception:
        pass

    return {
        "status": "healthy" if ollama_reachable and model_available else "degraded",
        "service": "small_llm",
        "ollama_reachable": ollama_reachable,
        "model_available": model_available,
        "configured_model": Config.SMALL_LLM_MODEL_NAME,
    }


@app.post("/query", response_model=QueryResponse)
def query_small_llm(request: QueryRequest) -> QueryResponse:
    """
    Query the Ollama service hosted on AUB HPC.

    This endpoint can use cached similar Q&A pairs to determine if there's an exact match
    or to provide context for better answers.

    Args:
        request: QueryRequest containing the user's math question and optional cached results

    Returns:
        QueryResponse with the answer, confidence, and exact match status

    Raises:
        HTTPException: If Ollama service is unavailable or returns an error
    """
    # Check for exact match in cached results (similarity >= 0.95)
    if request.cached_results:
        for cached in request.cached_results:
            if cached.similarity_score >= 0.95:
                # Found exact match, return cached answer
                return QueryResponse(
                    answer=cached.answer,
                    model_used=Config.SMALL_LLM_MODEL_NAME,
                    confidence=cached.similarity_score,
                    is_exact_match=True,
                )

    # No exact match - query LLM (with context if cached results exist)
    try:
        # Build prompt with context from cached results if available
        if request.cached_results and len(request.cached_results) > 0:
            context = "Here are some similar questions and answers for context:\n\n"
            for i, cached in enumerate(request.cached_results[:3], 1):
                context += f"{i}. Q: {cached.question}\n   A: {cached.answer}\n\n"
            context += f"Now answer this question: {request.query}"
            prompt = context
        else:
            prompt = request.query

        response = client.chat.completions.create(
            model=Config.SMALL_LLM_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            extra_body={"keep_alive": -1},
        )

        answer = response.choices[0].message.content or ""

        # Determine confidence based on whether we had cached context
        confidence = 0.7 if request.cached_results else 0.5

        return QueryResponse(
            answer=answer,
            model_used=Config.SMALL_LLM_MODEL_NAME,
            confidence=confidence,
            is_exact_match=False,
        )

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Small LLM service error: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
