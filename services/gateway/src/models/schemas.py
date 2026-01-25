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

    model: str = Field(default="math-tutor", description="Model to use")
    messages: list[ChatMessage] = Field(..., description="List of chat messages")
    temperature: Optional[float] = Field(
        default=0.7, ge=0.0, le=2.0, description="Sampling temperature"
    )
    max_tokens: Optional[int] = Field(default=None, description="Maximum tokens")


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


class Model(BaseModel):
    """OpenAI-compatible model object"""

    id: str = Field(..., description="Model identifier")
    object: Literal["model"] = Field(default="model")
    created: int = Field(..., description="Unix timestamp of creation")
    owned_by: str = Field(
        default="math-tutor", description="Organization that owns the model"
    )


class ModelListResponse(BaseModel):
    """OpenAI-compatible model list response"""

    object: Literal["list"] = Field(default="list")
    data: list[Model] = Field(..., description="List of available models")
