from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    service: str
    ollama_available: bool
    model_name: str
