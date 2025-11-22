from pydantic import BaseModel, Field


class ReformulatorRequest(BaseModel):
    """Request model for reformulating a query with context."""

    query: str = Field(..., description="User's current math question")
    previous_context: str = Field(
        default="", description="Previously summarized conversation context"
    )
    last_reply: str = Field(default="", description="Last reply from the assistant")


class ReformulatorResponse(BaseModel):
    """Response model from the reformulator."""

    lesson: str = Field(..., description="Identified lesson/topic from the curriculum")
    context: str = Field(..., description="Summarized context for this interaction")
    query: str = Field(..., description="Reformulated query for the LLM")
    location_in_chat: str = Field(
        ..., description="Position in conversation (e.g., 'start', 'middle', 'followup')"
    )
