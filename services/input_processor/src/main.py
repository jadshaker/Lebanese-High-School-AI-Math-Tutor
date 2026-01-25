import time

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from src.config import Config
from src.logging_utils import (
    StructuredLogger,
    generate_request_id,
    get_logs_by_request_id,
)
from src.metrics import http_request_duration_seconds, http_requests_total
from src.models.schemas import ProcessRequest, ProcessResponse

app = FastAPI(title="Math Tutor Input Processor Service")
logger = StructuredLogger("input_processor")


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Middleware to log all HTTP requests and responses, and record metrics"""
    request_id = generate_request_id()
    start_time = time.time()

    # Skip logging /metrics endpoint unless there's an error
    is_metrics_endpoint = request.url.path == "/metrics"

    # Log incoming request (skip /metrics)
    if not is_metrics_endpoint:
        logger.info(
            "Incoming request",
            context={
                "endpoint": request.url.path,
                "method": request.method,
                "client": request.client.host if request.client else "unknown",
            },
            request_id=request_id,
        )

    # Store request_id in request state for access in handlers
    request.state.request_id = request_id

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Record metrics (skip /metrics endpoint to avoid recursion)
        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="input_processor",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="input_processor",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

        # Log response (skip /metrics if status is 200)
        if not (is_metrics_endpoint and response.status_code == 200):
            logger.info(
                "Request completed",
                context={
                    "endpoint": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_seconds": round(duration, 3),
                },
                request_id=request_id,
            )

        # Add request_id to response headers
        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as e:
        duration = time.time() - start_time

        # Record error metrics
        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="input_processor",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="input_processor",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

        # Always log errors, even for /metrics
        logger.error(
            "Request failed",
            context={
                "endpoint": request.url.path,
                "method": request.method,
                "error": str(e),
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        raise


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "input_processor",
        "message": "Input processor service is running",
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/logs/{request_id}")
async def get_logs(request_id: str):
    """Get logs for a specific request ID"""
    logs = get_logs_by_request_id(request_id)
    return {"request_id": request_id, "logs": logs, "count": len(logs)}


@app.post("/process", response_model=ProcessResponse)
async def process_input(request: ProcessRequest, fastapi_request: FastAPIRequest):
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
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    logger.info(
        "Processing input",
        context={
            "input_type": request.type,
            "input_length": len(request.input),
        },
        request_id=request_id,
    )

    try:
        if request.type == "text":
            result = _process_text(request.input, request_id)
        elif request.type == "image":
            result = _process_image(request.input, request_id)
        else:
            logger.warning(
                "Invalid input type",
                context={"input_type": request.type},
                request_id=request_id,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Invalid input type: {request.type}. Must be 'text' or 'image'",
            )

        logger.info(
            "Input processed successfully",
            context={
                "input_type": result.input_type,
                "processed_length": len(result.processed_input),
                "preprocessing_applied": result.metadata.get(
                    "preprocessing_applied", []
                ),
            },
            request_id=request_id,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to process input",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


def _process_text(text: str, request_id: str) -> ProcessResponse:
    """
    Process text input.

    Performs basic preprocessing:
    - Strips leading/trailing whitespace
    - Validates length
    - Normalizes spacing

    Args:
        text: Raw text input
        request_id: Request ID for logging

    Returns:
        ProcessResponse with processed text
    """
    logger.debug(
        "Processing text input",
        context={"original_length": len(text)},
        request_id=request_id,
    )

    # Strip whitespace if configured
    processed = text.strip() if Config.PROCESSING.STRIP_WHITESPACE else text

    # Validate length
    if len(processed) == 0:
        logger.warning(
            "Empty input text after preprocessing",
            context={"original_length": len(text)},
            request_id=request_id,
        )
        raise HTTPException(status_code=400, detail="Input text cannot be empty")

    if len(processed) > Config.PROCESSING.MAX_INPUT_LENGTH:
        logger.warning(
            "Input text exceeds maximum length",
            context={
                "processed_length": len(processed),
                "max_length": Config.PROCESSING.MAX_INPUT_LENGTH,
            },
            request_id=request_id,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Input text exceeds maximum length of {Config.PROCESSING.MAX_INPUT_LENGTH} characters",
        )

    # Normalize multiple spaces to single space
    processed = " ".join(processed.split())

    logger.debug(
        "Text preprocessing complete",
        context={
            "original_length": len(text),
            "processed_length": len(processed),
        },
        request_id=request_id,
    )

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
    """
    Process image input (STUB).

    This is a stub implementation. In the full version, this would:
    - Decode base64 image data
    - Perform OCR to extract text
    - Validate image format and size
    - Return extracted mathematical notation

    Args:
        image_data: Image data (base64 encoded or URL)
        request_id: Request ID for logging

    Returns:
        ProcessResponse with stub acknowledgment
    """
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
