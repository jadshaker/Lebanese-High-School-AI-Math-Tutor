from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single chat message"""

    role: Literal["system", "user", "assistant"] = Field(
        ..., description="Role of the message sender"
    )
    content: str = Field(..., description="Message content")


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request"""

    model: str = Field(..., description="Model to use")
    messages: list[ChatMessage] = Field(..., description="List of chat messages")
    temperature: Optional[float] = Field(
        default=0.7, ge=0.0, le=2.0, description="Sampling temperature"
    )
    max_tokens: Optional[int] = Field(default=None, description="Maximum tokens")
    stream: Optional[bool] = Field(default=False, description="Stream responses")


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response (pass-through from Ollama)"""

    model_config = {"extra": "allow"}

    id: str
    object: str
    created: int
    model: str
    choices: list[dict[str, Any]]
