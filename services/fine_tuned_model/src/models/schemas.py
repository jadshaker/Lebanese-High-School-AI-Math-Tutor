from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request to query the fine-tuned model"""

    query: str = Field(..., description="User's question")


class QueryResponse(BaseModel):
    """Response from the fine-tuned model"""

    answer: str = Field(..., description="Generated answer")
    model_used: str = Field(..., description="Model identifier used for response")
