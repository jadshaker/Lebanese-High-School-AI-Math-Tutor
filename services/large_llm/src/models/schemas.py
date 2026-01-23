from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single chat message"""

    role: Literal["system", "user", "assistant"] = Field(
        ..., description="Role of the message sender"
    )
    content: str = Field(..., description="Message content")


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request"""

    model: str = Field(default="gpt-4o-mini", description="Model to use")
    messages: list[ChatMessage] = Field(..., description="List of chat messages")
    temperature: Optional[float] = Field(
        default=0.7, ge=0.0, le=2.0, description="Sampling temperature"
    )
    max_tokens: Optional[int] = Field(
        default=1000, gt=0, description="Maximum tokens to generate"
    )


class ChatCompletionMessageResponse(BaseModel):
    """The message in a chat completion choice"""

    role: Literal["assistant"] = Field(default="assistant")
    content: str = Field(..., description="Generated response content")


class ChatCompletionChoice(BaseModel):
    """A single choice in the completion response"""

    index: int = Field(..., description="Choice index")
    message: ChatCompletionMessageResponse = Field(..., description="Response message")
    finish_reason: Literal["stop", "length"] = Field(
        default="stop", description="Why generation stopped"
    )


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response"""

    id: str = Field(..., description="Unique completion ID")
    object: Literal["chat.completion"] = Field(default="chat.completion")
    created: int = Field(..., description="Unix timestamp of creation")
    model: str = Field(..., description="Model used for generation")
    choices: list[ChatCompletionChoice] = Field(..., description="Completion choices")
