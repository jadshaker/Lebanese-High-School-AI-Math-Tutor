from fastapi import HTTPException

from src.config import Config
from src.logging_utils import StructuredLogger
from src.models.schemas import ProcessResponse

logger = StructuredLogger("input_processor")


def process_input(text: str, input_type: str, request_id: str) -> ProcessResponse:
    """Process user input (text or image)."""
    logger.info(
        "Processing input",
        context={"input_type": input_type, "input_length": len(text)},
        request_id=request_id,
    )

    if input_type == "text":
        return _process_text(text, request_id)
    elif input_type == "image":
        return _process_image(text, request_id)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid input type: {input_type}. Must be 'text' or 'image'",
        )


def _process_text(text: str, request_id: str) -> ProcessResponse:
    """Process text input with basic preprocessing."""
    processed = text.strip() if Config.INPUT_PROCESSING.STRIP_WHITESPACE else text

    if len(processed) == 0:
        raise HTTPException(status_code=400, detail="Input text cannot be empty")

    if len(processed) > Config.INPUT_PROCESSING.MAX_INPUT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Input text exceeds maximum length of {Config.INPUT_PROCESSING.MAX_INPUT_LENGTH} characters",
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


def _process_image(image_data: str, request_id: str) -> ProcessResponse:
    """Process image input (STUB)."""
    logger.info(
        "Processing image input (stub)",
        context={"image_data_length": len(image_data)},
        request_id=request_id,
    )

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
