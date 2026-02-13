from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Source of the answer"""

    API_LLM = "api_llm"
    SMALL_LLM = "small_llm"
    FINE_TUNED = "fine_tuned"
    HUMAN = "human"
    AUTO_GENERATED = "auto_generated"


class SearchFilters(BaseModel):
    """Filters for vector search"""

    lesson: Optional[str] = Field(None, description="Filter by lesson/chapter")
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    source: Optional[SourceType] = None


class SearchRequest(BaseModel):
    """Request for vector similarity search"""

    embedding: list[float] = Field(..., description="Query embedding vector")
    top_k: int = Field(5, ge=1, le=20, description="Number of results to return")
    threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum similarity")
    filters: Optional[SearchFilters] = None


class SearchResultItem(BaseModel):
    """Single search result"""

    id: str
    score: float = Field(..., description="Cosine similarity score")
    question_text: str
    answer_text: str
    lesson: Optional[str] = None
    confidence: float
    source: SourceType
    usage_count: int = 0


class SearchResponse(BaseModel):
    """Response from vector search"""

    results: list[SearchResultItem]
    total_found: int


class QuestionCreate(BaseModel):
    """Request to add a new question to cache"""

    question_text: str = Field(..., description="Original question text")
    reformulated_text: str = Field(..., description="Reformulated question")
    answer_text: str = Field(..., description="Answer to the question")
    embedding: list[float] = Field(..., description="Embedding vector")
    lesson: Optional[str] = Field(None, description="Lesson/chapter name")
    source: SourceType = Field(SourceType.API_LLM)
    confidence: float = Field(0.9, ge=0.0, le=1.0)


class QuestionResponse(BaseModel):
    """Response after creating/getting a question"""

    id: str
    question_text: str
    reformulated_text: str
    answer_text: str
    lesson: Optional[str]
    source: SourceType
    confidence: float
    usage_count: int
    positive_feedback: int
    negative_feedback: int
    created_at: datetime
    updated_at: datetime


class QuestionUpdate(BaseModel):
    """Request to update a question"""

    answer_text: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    lesson: Optional[str] = None


class FeedbackRequest(BaseModel):
    """Request to submit feedback"""

    positive: bool = Field(..., description="True for positive, False for negative")


class FeedbackResponse(BaseModel):
    """Response after feedback submission"""

    id: str
    positive_feedback: int
    negative_feedback: int
    feedback_score: float = Field(..., description="Ratio of positive feedback")


class InteractionCreate(BaseModel):
    """Request to create an interaction node (user input + system response)"""

    question_id: str = Field(..., description="Root question this belongs to")
    parent_id: Optional[str] = Field(
        None, description="Parent node ID (null = direct child of question)"
    )
    user_input: str = Field(..., description="What the user said")
    user_input_embedding: list[float] = Field(
        ..., description="Embedding of user_input"
    )
    system_response: str = Field(..., description="System's response to user")


class InteractionResponse(BaseModel):
    """Response for an interaction node"""

    id: str
    question_id: str
    parent_id: Optional[str]
    user_input: str
    system_response: str
    depth: int
    source: SourceType
    created_at: datetime


class SearchChildrenRequest(BaseModel):
    """Request to search children of a node by embedding similarity"""

    question_id: str = Field(..., description="Question ID")
    parent_id: Optional[str] = Field(
        None, description="Parent node ID (null = search direct children of question)"
    )
    user_input_embedding: list[float] = Field(..., description="User input to match")
    threshold: float = Field(0.7, ge=0.0, le=1.0, description="Minimum similarity")


class SearchChildrenResponse(BaseModel):
    """Response from searching children"""

    is_cache_hit: bool
    match_score: Optional[float] = Field(None, description="Similarity score if hit")
    matched_node: Optional[InteractionResponse] = Field(
        None, description="Matched node if hit"
    )
    parent_id: Optional[str] = Field(
        None, description="Parent to use for creating new node on miss"
    )


class ConversationPathNode(BaseModel):
    """Node in a conversation path"""

    id: str
    user_input: str
    system_response: str
    depth: int


class ConversationPathResponse(BaseModel):
    """Full conversation path from question to current node"""

    question_id: str
    question_text: str
    answer_text: str
    path: list[ConversationPathNode]
    total_depth: int


class BulkCreateRequest(BaseModel):
    """Request to create multiple questions at once"""

    questions: list[QuestionCreate]


class BulkCreateResponse(BaseModel):
    """Response from bulk creation"""

    created_count: int
    ids: list[str]


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    service: str
    qdrant_connected: bool
    collections: dict[str, int] = Field(
        ..., description="Collection names and point counts"
    )
