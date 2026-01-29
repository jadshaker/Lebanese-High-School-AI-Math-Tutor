from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# === Enums ===


class ChatPhase(str, Enum):
    """Current phase in the chat"""

    PROCESSING = "processing"
    ANSWERING = "answering"
    TUTORING = "tutoring"
    COMPLETED = "completed"


class RetrievalTier(str, Enum):
    """Confidence tier for retrieval"""

    TIER_1_DIRECT = "tier_1_direct"  # score > 0.90
    TIER_2_VALIDATE = "tier_2_validate"  # score 0.70-0.90
    TIER_3_CONTEXT = "tier_3_context"  # score 0.50-0.70
    TIER_4_GENERATE = "tier_4_generate"  # score < 0.50


# === Legacy Schemas (keep for backward compatibility) ===


class QueryRequest(BaseModel):
    """Legacy query request"""

    query: str = Field(..., description="User's math question")
    use_large_llm: bool = Field(False)


class FinalResponse(BaseModel):
    """Legacy response"""

    answer: str
    path_taken: str
    verified: bool
    fallback_used: bool = False


# === New Chat Pipeline Schemas ===


class ChatRequest(BaseModel):
    """Request to start a new chat or continue existing"""

    query: str = Field(..., description="User's math question or response")
    session_id: Optional[str] = Field(
        None, description="Existing session ID to continue"
    )
    user_id: Optional[str] = Field(None, description="Optional user identifier")


class TutoringQuestion(BaseModel):
    """A tutoring question being asked"""

    node_id: str
    question: str
    depth: int


class ChatResponse(BaseModel):
    """Response from chat endpoint"""

    session_id: str
    phase: ChatPhase
    message: str = Field(..., description="The response message to show user")

    # Retrieval info
    retrieval_score: Optional[float] = None
    retrieval_tier: Optional[RetrievalTier] = None
    source: Optional[str] = None  # "cache" | "small_llm" | "api_llm"

    # Tutoring info (if in tutoring phase)
    tutoring_question: Optional[TutoringQuestion] = None
    tutoring_depth: int = 0
    can_skip: bool = True

    # Final answer (if completed or skipped)
    final_answer: Optional[str] = None

    # Metadata
    lesson: Optional[str] = None


class TutoringResponseRequest(BaseModel):
    """User's response to a tutoring question"""

    response: str = Field(..., description="User's response to the tutoring question")


class SkipRequest(BaseModel):
    """Request to skip tutoring and get the answer"""

    reason: Optional[str] = Field(None, description="Optional reason for skipping")


class SessionStateResponse(BaseModel):
    """Current state of a session"""

    session_id: str
    phase: ChatPhase
    original_query: Optional[str]
    reformulated_query: Optional[str]
    lesson: Optional[str]
    retrieved_answer: Optional[str]
    retrieval_score: Optional[float]
    tutoring_depth: int
    current_node_id: Optional[str]
    message_count: int


# === Service Call Schemas ===


class ReformulatorResult(BaseModel):
    """Result from reformulator service"""

    lesson: Optional[str]
    context: Optional[str]
    reformulated_query: str
    location_in_chat: str


class EmbeddingResult(BaseModel):
    """Result from embedding service"""

    embedding: list[float]
    model: str
    dimensions: int


class VectorSearchResult(BaseModel):
    """Single result from vector search"""

    id: str
    score: float
    question_text: str
    answer_text: str
    lesson: Optional[str]
    tutoring_root_id: Optional[str]


class IntentResult(BaseModel):
    """Result from intent classifier"""

    intent: str
    confidence: float
    method: str


class GraphTraverseResult(BaseModel):
    """Result from graph traversal"""

    next_node_id: Optional[str]
    content: Optional[str]
    is_cache_hit: bool
    match_score: Optional[float]
    context_for_generation: Optional[dict[str, Any]]


# === Health Check ===


class ServiceHealth(BaseModel):
    """Health status of a single service"""

    status: str
    details: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class GatewayHealthResponse(BaseModel):
    """Gateway health check response"""

    status: str
    service: str
    services: dict[str, ServiceHealth]
