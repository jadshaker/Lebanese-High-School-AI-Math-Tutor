from pydantic import BaseModel, Field


class ReformulateRequest(BaseModel):
    """Request to reformulate processed input"""

    processed_input: str = Field(..., description="Processed user input")
    input_type: str = Field(..., description="Type of input: 'text' or 'image'")


class ReformulateResponse(BaseModel):
    """Response containing reformulated query"""

    reformulated_query: str = Field(..., description="Improved, clearer question")
    original_input: str = Field(..., description="Original processed input")
    improvements_made: list[str] = Field(
        default_factory=list, description="List of improvements applied"
    )
