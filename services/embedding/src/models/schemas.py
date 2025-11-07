from pydantic import BaseModel, Field


class EmbedRequest(BaseModel):
    """Request to embed text"""

    text: str = Field(..., description="Text to embed")


class EmbedResponse(BaseModel):
    """Response containing embedding vector"""

    embedding: list[float] = Field(..., description="Embedding vector")
    model: str = Field(..., description="Model used for embedding")
    dimensions: int = Field(..., description="Dimension of embedding vector")
