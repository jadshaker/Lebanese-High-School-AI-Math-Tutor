from pydantic import BaseModel, Field


class ComplexityRequest(BaseModel):
    """Request for complexity assessment"""

    query: str = Field(..., description="The math question to assess")


class ComplexityResponse(BaseModel):
    """Response with complexity assessment"""

    complexity_score: float = Field(
        ..., description="Complexity score between 0.0 (simple) and 1.0 (complex)"
    )
    is_complex: bool = Field(..., description="Whether the query is complex")
    reasoning: str = Field(..., description="Explanation of the complexity assessment")
