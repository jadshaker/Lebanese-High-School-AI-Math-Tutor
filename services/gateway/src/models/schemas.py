from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """User query request"""

    input: str = Field(..., description="User's math question or input")
    type: Literal["text", "image"] = Field(
        "text", description="Type of input (text or image)"
    )


class FinalResponse(BaseModel):
    """Final response to user"""

    answer: str = Field(..., description="Final answer to the user's query")
    source: str = Field(..., description="LLM source (small_llm or large_llm)")
    used_cache: bool = Field(..., description="Whether cache was used")
    metadata: Dict[str, Any] = Field(
        ..., description="Metadata from processing and retrieval"
    )
