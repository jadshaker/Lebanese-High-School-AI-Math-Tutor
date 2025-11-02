from typing import Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """Request to generate an answer"""

    query: str = Field(..., description="User's math question")


class GenerateResponse(BaseModel):
    """Response from answer generation"""

    answer: str = Field(..., description="Generated answer")
    model_used: str = Field(
        ..., description="Model identifier that generated the response"
    )
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Model's confidence in answer"
    )
