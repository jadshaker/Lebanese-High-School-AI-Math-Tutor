from pydantic import BaseModel, Field


class RetrieveAnswerRequest(BaseModel):
    """Request to retrieve an answer for a user query"""

    query: str = Field(..., description="User's math question")


class RetrieveAnswerResponse(BaseModel):
    """Response with the final answer and metadata"""

    answer: str = Field(..., description="Final answer to the question")
    source: str = Field(
        ..., description="Source of the answer: 'small_llm' or 'large_llm'"
    )
    used_cache: bool = Field(..., description="Whether cached results were used")
    confidence: float | None = Field(
        None, description="Confidence score if from small_llm"
    )
