from pydantic import BaseModel, Field


class CachedResult(BaseModel):
    """A cached Q&A result from similarity search"""

    question: str = Field(..., description="Cached question")
    answer: str = Field(..., description="Cached answer")
    similarity_score: float = Field(..., description="Similarity score")


class QueryRequest(BaseModel):
    """Request model for querying the small LLM."""

    query: str = Field(..., description="User's math question")
    cached_results: list[CachedResult] | None = Field(
        None, description="Optional cached similar Q&A pairs from vector search"
    )


class QueryResponse(BaseModel):
    """Response model from the small LLM."""

    answer: str | None = Field(..., description="Answer from the small LLM")
    model_used: str = Field(default="ollama", description="Model identifier")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in the answer"
    )
    is_exact_match: bool = Field(
        ..., description="Whether an exact match was found in cached results"
    )
