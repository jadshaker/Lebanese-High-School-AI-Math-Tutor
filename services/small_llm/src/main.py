import json
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from src.config import Config
from src.models.schemas import QueryRequest, QueryResponse

app = FastAPI(title="Small LLM Service", version="1.0.0")

# CORS for UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(
    base_url=f"{Config.OLLAMA_SERVICE_URL}/v1",
    api_key="ollama",
)


@app.get("/health")
def health_check() -> dict[str, str | bool]:
    """Health check endpoint that verifies Ollama connectivity and model availability."""
    ollama_reachable = False
    model_available = False

    try:
        req = Request(
            f"{Config.OLLAMA_SERVICE_URL}/api/tags",
            method="GET",
        )

        with urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
            ollama_reachable = True

            models = result.get("models", [])
            model_available = any(
                model.get("name") == Config.OLLAMA_MODEL_NAME for model in models
            )

    except Exception:
        pass

    return {
        "status": "healthy" if ollama_reachable and model_available else "degraded",
        "service": "small_llm",
        "ollama_reachable": ollama_reachable,
        "model_available": model_available,
        "configured_model": Config.OLLAMA_MODEL_NAME,
    }


@app.post("/query", response_model=QueryResponse)
def query_small_llm(request: QueryRequest) -> QueryResponse:
    """
    Query the Ollama service hosted on AUB HPC.

    This endpoint forwards the query to the Ollama server and returns the response.

    Args:
        request: QueryRequest containing the user's math question

    Returns:
        QueryResponse with the answer from Ollama

    Raises:
        HTTPException: If Ollama service is unavailable or returns an error
    """
    try:
        response = client.chat.completions.create(
            model=Config.OLLAMA_MODEL_NAME,
            messages=[{"role": "user", "content": request.query}],
            extra_body={"keep_alive": -1},
        )

        answer = response.choices[0].message.content or ""
        return QueryResponse(answer=answer, model_used=Config.OLLAMA_MODEL_NAME)

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Small LLM service error: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
