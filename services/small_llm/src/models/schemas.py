from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request model for querying the small LLM."""

    query: str = Field(..., description="User's math question")


class QueryResponse(BaseModel):
    """Response model from the small LLM."""

    answer: str = Field(..., description="Answer from the small LLM")
    model_used: str = Field(default="ollama", description="Model identifier")
