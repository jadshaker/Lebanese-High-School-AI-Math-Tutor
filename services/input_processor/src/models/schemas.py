from pydantic import BaseModel, Field


class ProcessRequest(BaseModel):
    """Request to process user input"""

    input: str = Field(..., description="User input (text or image data)")
    type: str = Field(..., description="Input type: 'text' or 'image'")


class ProcessResponse(BaseModel):
    """Response containing processed input"""

    processed_input: str = Field(..., description="Processed user input")
    input_type: str = Field(..., description="Type of input processed")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
