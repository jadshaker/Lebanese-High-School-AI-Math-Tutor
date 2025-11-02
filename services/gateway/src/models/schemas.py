from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """User query request"""

    query: str = Field(..., description="User's math question")


class FinalResponse(BaseModel):
    """Final response to user"""

    answer: str = Field(..., description="Final answer to the user's query")
    path_taken: str = Field(
        ..., description="Which path was taken (cache/small/local/large)"
    )
    verified: bool = Field(..., description="Whether answer was verified as correct")
    fallback_used: bool = Field(
        False, description="Whether fallback to large LLM was used"
    )
