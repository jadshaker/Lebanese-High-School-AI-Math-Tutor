from pydantic import BaseModel, Field


class ProcessQueryRequest(BaseModel):
    """Request to process user query through Phase 1 pipeline"""

    input: str = Field(..., description="User input (text or image data)")
    type: str = Field(..., description="Input type: 'text' or 'image'")


class ProcessQueryResponse(BaseModel):
    """Response containing reformulated query and processing metadata"""

    reformulated_query: str = Field(..., description="Improved, clearer question")
    original_input: str = Field(..., description="Original user input")
    input_type: str = Field(..., description="Type of input processed")
    processing_metadata: dict = Field(
        default_factory=dict,
        description="Metadata from input_processor and reformulator",
    )
