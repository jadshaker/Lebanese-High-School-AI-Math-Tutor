from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# === Gateway / API Schemas ===


class ConfidenceTier(str, Enum):
    """4-tier confidence routing levels"""

    TIER_1_SMALL_LLM_VALIDATE_OR_GENERATE = "tier_1_small_llm_validate_or_generate"
    TIER_2_SMALL_LLM_CONTEXT = "tier_2_small_llm_context"
    TIER_3_FINE_TUNED = "tier_3_fine_tuned"
    TIER_4_LARGE_LLM = "tier_4_large_llm"


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
    question_id: Optional[str] = Field(
        None, description="Question ID from initial query"
    )
    original_question: Optional[str] = Field(None, description="Original question text")
    original_answer: Optional[str] = Field(
        None, description="Original answer for context"
    )


class TutoringResponse(BaseModel):
    """Response from tutoring interaction"""

    session_id: str
    tutor_message: str
    is_complete: bool = Field(default=False, description="Whether tutoring is complete")
    next_prompt: Optional[str] = Field(None, description="Next question if continuing")
    intent: Optional[str] = Field(None, description="Classified intent")
    cache_hit: bool = Field(
        default=False, description="Whether response was from cache"
    )


class RetrievalMetadata(BaseModel):
    """Metadata about how an answer was retrieved"""

    tier: ConfidenceTier
    confidence_score: float
    cache_hit: bool
    llm_used: Optional[str] = None
    cache_reused: Optional[bool] = None


# === Input Processor Schemas ===


class ProcessRequest(BaseModel):
    """Request to process user input"""

    input: str = Field(..., description="User input (text or image data)")
    type: str = Field(..., description="Input type: 'text' or 'image'")


class ProcessResponse(BaseModel):
    """Response containing processed input"""

    processed_input: str = Field(..., description="Processed user input")
    input_type: str = Field(..., description="Type of input processed")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


# === Reformulator Schemas ===


class ReformulatorConversationMessage(BaseModel):
    """A message in the conversation history for reformulation"""

    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ReformulateRequest(BaseModel):
    """Request to reformulate processed input"""

    processed_input: str = Field(..., description="Processed user input")
    input_type: str = Field(..., description="Type of input: 'text' or 'image'")
    conversation_history: Optional[list[ReformulatorConversationMessage]] = Field(
        None, description="Previous conversation for context"
    )


class ReformulateResponse(BaseModel):
    """Response containing reformulated query"""

    reformulated_query: str = Field(..., description="Improved, clearer question")
    original_input: str = Field(..., description="Original processed input")
    improvements_made: list[str] = Field(
        default_factory=list, description="List of improvements applied"
    )
    is_math_related: bool = Field(
        default=True, description="Whether the input is math-related"
    )


# === Embedding Schemas ===


class EmbedRequest(BaseModel):
    """Request to embed text"""

    text: str = Field(..., description="Text to embed")


class EmbedResponse(BaseModel):
    """Response containing embedding vector"""

    embedding: list[float] = Field(..., description="Embedding vector")
    model: str = Field(..., description="Model used for embedding")
    dimensions: int = Field(..., description="Dimension of embedding vector")


# === Intent Classifier Schemas ===


class IntentCategory(str, Enum):
    """User intent categories"""

    AFFIRMATIVE = "affirmative"
    NEGATIVE = "negative"
    PARTIAL = "partial"
    QUESTION = "question"
    SKIP = "skip"
    OFF_TOPIC = "off_topic"


class ClassificationMethod(str, Enum):
    """How the classification was made"""

    RULE_BASED = "rule_based"
    LLM_BASED = "llm_based"
    HYBRID = "hybrid"


class ClassifyRequest(BaseModel):
    """Request to classify user intent"""

    text: str = Field(..., description="User response text to classify")
    context: Optional[str] = Field(
        None, description="Optional context (tutor's previous question)"
    )


class ClassifyResponse(BaseModel):
    """Classification result"""

    intent: IntentCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    method: ClassificationMethod
    matched_patterns: Optional[list[str]] = Field(
        None, description="Patterns matched (for rule-based)"
    )


class BatchClassifyRequest(BaseModel):
    """Request to classify multiple texts"""

    texts: list[str]
    context: Optional[str] = None


class BatchClassifyResponse(BaseModel):
    """Batch classification results"""

    results: list[ClassifyResponse]


# === Session Schemas ===


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
    phase: SessionPhase = SessionPhase.INITIAL
    original_query: Optional[str] = None
    reformulated_query: Optional[str] = None
    identified_lesson: Optional[str] = None
    retrieved_answer: Optional[str] = None
    retrieval_score: Optional[float] = None
    retrieval_source: Optional[str] = None
    tutoring: TutoringState = Field(default_factory=TutoringState)
    messages: list[ConversationMessage] = Field(default_factory=list)
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


# === Vector Cache Schemas ===


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
    """Request to create an interaction node"""

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
    parent_id: Optional[str] = Field(None, description="Parent node ID")
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
