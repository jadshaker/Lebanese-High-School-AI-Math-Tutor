import json
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from openai import OpenAI
from src.config import Config
from src.models.schemas import QueryRequest, QueryResponse

app = FastAPI(title="Fine-Tuned Model Service", version="1.0.0")

client = OpenAI(
    base_url=f"{Config.FINE_TUNED_MODEL_SERVICE_URL}/v1",
    api_key="ollama",
)


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


@app.post("/query", response_model=QueryResponse)
def query_fine_tuned_model(request: QueryRequest) -> QueryResponse:
    """
    Query the fine-tuned model via Ollama service.

    This endpoint forwards the query to the Ollama server and returns the response.

    Args:
        request: QueryRequest containing the user's question

    Returns:
        QueryResponse with the answer from the fine-tuned model

    Raises:
        HTTPException: If Ollama service is unavailable or returns an error
    """
    try:
        response = client.chat.completions.create(
            model=Config.FINE_TUNED_MODEL_NAME,
            messages=[{"role": "user", "content": request.query}],
            extra_body={"keep_alive": -1},
        )

        answer = response.choices[0].message.content or ""
        return QueryResponse(answer=answer, model_used=Config.FINE_TUNED_MODEL_NAME)

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Fine-tuned model service error: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)
