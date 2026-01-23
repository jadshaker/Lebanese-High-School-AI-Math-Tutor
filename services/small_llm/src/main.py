import json
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from src.config import Config
from src.models.schemas import ChatCompletionRequest, ChatCompletionResponse

app = FastAPI(title="Small LLM Service", version="1.0.0")


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


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """
    OpenAI-compatible chat completions endpoint.
    Forwards requests to Ollama's OpenAI-compatible API.

    Args:
        request: ChatCompletionRequest with messages and model

    Returns:
        ChatCompletionResponse from Ollama

    Raises:
        HTTPException: If Ollama service is unavailable or returns an error
    """
    try:
        # Forward request to Ollama's OpenAI-compatible endpoint
        ollama_url = f"{Config.SMALL_LLM_SERVICE_URL}/v1/chat/completions"

        # Build request payload
        payload: dict[str, object] = {
            "model": request.model or Config.SMALL_LLM_MODEL_NAME,
            "messages": [
                {"role": msg.role, "content": msg.content} for msg in request.messages
            ],
            "keep_alive": -1,
        }

        # Add optional parameters
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stream is not None:
            payload["stream"] = request.stream

        # Make request to Ollama
        req = Request(
            ollama_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
            return ChatCompletionResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Small LLM service error: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
