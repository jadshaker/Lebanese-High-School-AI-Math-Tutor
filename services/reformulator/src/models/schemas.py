from typing import Optional

from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    """A message in the conversation history"""

    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ReformulateRequest(BaseModel):
    """Request to reformulate processed input"""

    processed_input: str = Field(..., description="Processed user input")
    input_type: str = Field(..., description="Type of input: 'text' or 'image'")
    conversation_history: Optional[list[ConversationMessage]] = Field(
        None, description="Previous conversation for context"
    )


class ReformulateResponse(BaseModel):
    """Response containing reformulated query"""

    reformulated_query: str = Field(..., description="Improved, clearer question")
    original_input: str = Field(..., description="Original processed input")
    improvements_made: list[str] = Field(
        default_factory=list, description="List of improvements applied"
    )
