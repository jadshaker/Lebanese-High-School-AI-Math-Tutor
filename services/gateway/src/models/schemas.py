from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ConfidenceTier(str, Enum):
    """5-tier confidence routing levels"""

    TIER_1_DIRECT_CACHE = "tier_1_direct_cache"
    TIER_2_SMALL_LLM_VALIDATE = "tier_2_small_llm_validate"
    TIER_3_SMALL_LLM_CONTEXT = "tier_3_small_llm_context"
    TIER_4_FINE_TUNED = "tier_4_fine_tuned"
    TIER_5_LARGE_LLM = "tier_5_large_llm"


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


class TutoringRequest(BaseModel):
    """Request for tutoring interaction"""

    session_id: str = Field(..., description="Session ID for stateful tutoring")
    user_response: str = Field(..., description="User's response to tutor prompt")
    question_id: Optional[str] = Field(None, description="Question ID from initial query")
    original_question: Optional[str] = Field(None, description="Original question text")
    original_answer: Optional[str] = Field(None, description="Original answer for context")


class TutoringResponse(BaseModel):
    """Response from tutoring interaction"""

    session_id: str
    tutor_message: str
    is_complete: bool = Field(default=False, description="Whether tutoring is complete")
    next_prompt: Optional[str] = Field(None, description="Next question if continuing")
    intent: Optional[str] = Field(None, description="Classified intent")
    cache_hit: bool = Field(default=False, description="Whether response was from cache")


class RetrievalMetadata(BaseModel):
    """Metadata about how an answer was retrieved"""

    tier: ConfidenceTier
    confidence_score: float
    cache_hit: bool
    llm_used: Optional[str] = None
    validation_passed: Optional[bool] = None
