from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SessionPhase(str, Enum):
    """Current phase in the tutoring pipeline"""

    INITIAL = "initial"
    REFORMULATION = "reformulation"
    RETRIEVAL = "retrieval"
    TUTORING = "tutoring"
    COMPLETED = "completed"


class MessageRole(str, Enum):
    """Role in conversation"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationMessage(BaseModel):
    """Single message in conversation history"""

    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict[str, Any]] = None


class TutoringState(BaseModel):
    """State of tutoring graph traversal"""

    question_id: Optional[str] = None
    current_node_id: Optional[str] = None
    traversal_path: list[str] = Field(default_factory=list)
    depth: int = 0
    is_new_branch: bool = False


class SessionData(BaseModel):
    """Complete session data"""

    session_id: str
    user_id: Optional[str] = None

    # Pipeline state
    phase: SessionPhase = SessionPhase.INITIAL

    # Query processing
    original_query: Optional[str] = None
    reformulated_query: Optional[str] = None
    identified_lesson: Optional[str] = None

    # Retrieval results
    retrieved_answer: Optional[str] = None
    retrieval_score: Optional[float] = None
    retrieval_source: Optional[str] = None

    # Tutoring state
    tutoring: TutoringState = Field(default_factory=TutoringState)

    # Conversation
    messages: list[ConversationMessage] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)


class SessionCreateRequest(BaseModel):
    """Request to create a new session"""

    user_id: Optional[str] = None
    initial_query: Optional[str] = None


class SessionCreateResponse(BaseModel):
    """Response after creating session"""

    session_id: str
    created_at: datetime


class SessionGetResponse(BaseModel):
    """Full session data response"""

    session_id: str
    user_id: Optional[str]
    phase: SessionPhase
    original_query: Optional[str]
    reformulated_query: Optional[str]
    identified_lesson: Optional[str]
    retrieved_answer: Optional[str]
    retrieval_score: Optional[float]
    retrieval_source: Optional[str]
    tutoring: TutoringState
    message_count: int
    created_at: datetime
    last_activity: datetime


class SessionUpdateRequest(BaseModel):
    """Request to update session state"""

    phase: Optional[SessionPhase] = None
    original_query: Optional[str] = None
    reformulated_query: Optional[str] = None
    identified_lesson: Optional[str] = None
    retrieved_answer: Optional[str] = None
    retrieval_score: Optional[float] = None
    retrieval_source: Optional[str] = None


class TutoringUpdateRequest(BaseModel):
    """Request to update tutoring state"""

    question_id: Optional[str] = None
    current_node_id: Optional[str] = None
    depth: Optional[int] = None
    add_to_path: Optional[str] = Field(None, description="Node ID to add to path")
    is_new_branch: Optional[bool] = None


class MessageAddRequest(BaseModel):
    """Request to add a message to history"""

    role: MessageRole
    content: str
    metadata: Optional[dict[str, Any]] = None


class MessageHistoryResponse(BaseModel):
    """Response with conversation history"""

    session_id: str
    messages: list[ConversationMessage]
    total_count: int


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    service: str
    active_sessions: int
    uptime_seconds: float
