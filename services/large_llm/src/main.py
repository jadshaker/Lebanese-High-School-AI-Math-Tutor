import time
import uuid

from fastapi import FastAPI, HTTPException
from openai import OpenAI
from src.config import Config
from src.models.schemas import (
    ChatCompletionChoice,
    ChatCompletionMessageResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
)

app = FastAPI(title="Math Tutor API Large LLM Service")

# Initialize OpenAI client
client = OpenAI(api_key=Config.API_KEYS.OPENAI) if Config.API_KEYS.OPENAI else None


@app.get("/health")
async def health():
    """Health check endpoint"""
    api_configured = Config.API_KEYS.OPENAI is not None
    return {
        "status": "healthy",
        "service": "large_llm",
        "model": "gpt-4o-mini",
        "api_configured": api_configured,
    }


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint.
    Generates answers using OpenAI's GPT-4 API.
    Falls back to dummy response if API key is not configured.
    """
    if not client:
        # Fallback to dummy response if no API key
        last_user_message = next(
            (msg.content for msg in reversed(request.messages) if msg.role == "user"),
            "No user message",
        )
        dummy_answer = (
            f"[Dummy Response] API key not configured. Query: {last_user_message}"
        )

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model="dummy-fallback",
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionMessageResponse(content=dummy_answer),
                    finish_reason="stop",
                )
            ],
        )

    try:
        # Call OpenAI API with the provided messages
        response = client.chat.completions.create(
            model=request.model,
            messages=[
                {"role": msg.role, "content": msg.content}  # type: ignore[misc]
                for msg in request.messages
            ],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        answer = response.choices[0].message.content or ""

        return ChatCompletionResponse(
            id=response.id,
            created=response.created,
            model=response.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionMessageResponse(content=answer),
                    finish_reason="stop",
                )
            ],
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"OpenAI API error: {str(e)}",
        )
