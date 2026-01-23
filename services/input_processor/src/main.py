from fastapi import FastAPI, HTTPException
from src.config import Config
from src.models.schemas import ProcessRequest, ProcessResponse

app = FastAPI(title="Math Tutor Input Processor Service")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "input_processor",
        "message": "Input processor service is running",
    }


@app.post("/process", response_model=ProcessResponse)
async def process_input(request: ProcessRequest):
    """
    Process user input (text or image).

    For text input, performs basic preprocessing like trimming whitespace
    and length validation.

    For image input, returns a stub response acknowledging receipt.

    Args:
        request: ProcessRequest with input data and type

    Returns:
        ProcessResponse with processed input and metadata
    """
    if request.type == "text":
        return _process_text(request.input)
    elif request.type == "image":
        return _process_image(request.input)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid input type: {request.type}. Must be 'text' or 'image'",
        )


def _process_text(text: str) -> ProcessResponse:
    """
    Process text input.

    Performs basic preprocessing:
    - Strips leading/trailing whitespace
    - Validates length
    - Normalizes spacing

    Args:
        text: Raw text input

    Returns:
        ProcessResponse with processed text
    """
    # Strip whitespace if configured
    processed = text.strip() if Config.PROCESSING.STRIP_WHITESPACE else text

    # Validate length
    if len(processed) == 0:
        raise HTTPException(status_code=400, detail="Input text cannot be empty")

    if len(processed) > Config.PROCESSING.MAX_INPUT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Input text exceeds maximum length of {Config.PROCESSING.MAX_INPUT_LENGTH} characters",
        )

    # Normalize multiple spaces to single space
    processed = " ".join(processed.split())

    return ProcessResponse(
        processed_input=processed,
        input_type="text",
        metadata={
            "original_length": len(text),
            "processed_length": len(processed),
            "preprocessing_applied": ["strip_whitespace", "normalize_spacing"],
        },
    )


def _process_image(image_data: str) -> ProcessResponse:
    """
    Process image input (STUB).

    This is a stub implementation. In the full version, this would:
    - Decode base64 image data
    - Perform OCR to extract text
    - Validate image format and size
    - Return extracted mathematical notation

    Args:
        image_data: Image data (base64 encoded or URL)

    Returns:
        ProcessResponse with stub acknowledgment
    """
    return ProcessResponse(
        processed_input="Image input received",
        input_type="image",
        metadata={
            "note": "Image processing not yet implemented",
            "planned_features": [
                "OCR text extraction",
                "Math notation recognition",
                "Image validation",
            ],
            "image_data_length": len(image_data),
        },
    )
