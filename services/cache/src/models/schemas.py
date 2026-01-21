from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Request to search for similar Q&A pairs in cache"""

    embedding: list[float] = Field(..., description="Query embedding vector")
    top_k: int = Field(
        default=3, ge=1, le=10, description="Number of results to return"
    )


class CachedResult(BaseModel):
    """A single cached Q&A result with similarity score"""

    question: str = Field(..., description="Cached question")
    answer: str = Field(..., description="Cached answer")
    similarity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Cosine similarity score"
    )


class SearchResponse(BaseModel):
    """Response containing similar Q&A pairs from cache"""

    results: list[CachedResult] = Field(..., description="List of similar Q&A pairs")
    count: int = Field(..., description="Number of results returned")


class SaveRequest(BaseModel):
    """Request to save Q&A pair to cache"""

    question: str = Field(..., description="Question to cache")
    answer: str = Field(..., description="Answer to cache")
    embedding: list[float] = Field(..., description="Question embedding vector")


class SaveResponse(BaseModel):
    """Response from save operation"""

    status: str = Field(..., description="Status of save operation")
    message: str = Field(..., description="Status message")


class TutoringRequest(BaseModel):
    """Request to check tutoring cache"""

    question: str = Field(..., description="Question to check in tutoring cache")


class TutoringResponse(BaseModel):
    """Response from tutoring cache check"""

    found: bool = Field(..., description="Whether tutoring content was found")
    data: dict | None = Field(None, description="Tutoring data if found")
