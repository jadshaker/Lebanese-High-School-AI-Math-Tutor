import json
import time
from urllib.request import Request, urlopen

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
from src.models.schemas import ReformulateRequest, ReformulateResponse

app = FastAPI(title="Math Tutor Reformulator Service")
logger = StructuredLogger("reformulator")


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Middleware to log all HTTP requests and responses, and record metrics"""
    incoming_request_id = request.headers.get("X-Request-ID")
    request_id = incoming_request_id if incoming_request_id else generate_request_id()
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
                service="reformulator",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="reformulator",
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
                service="reformulator",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="reformulator",
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
    # Check if Small LLM service is reachable
    small_llm_healthy = False
    try:
        req = Request(
            f"{Config.SERVICES.SMALL_LLM_URL}/health",
            method="GET",
        )
        with urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
            small_llm_healthy = result.get("status") == "healthy"
    except Exception:
        pass

    return {
        "status": "healthy" if small_llm_healthy else "degraded",
        "service": "reformulator",
        "small_llm_service": "reachable" if small_llm_healthy else "unreachable",
        "message": "Reformulator service is running",
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


@app.post("/reformulate", response_model=ReformulateResponse)
async def reformulate_query(
    request: ReformulateRequest, fastapi_request: FastAPIRequest
):
    """
    Reformulate user input to improve clarity and precision.

    Uses an LLM to:
    - Standardize mathematical notation
    - Improve question clarity and completeness
    - Fix grammar and structure
    - Make questions more precise for problem-solving

    Args:
        request: ReformulateRequest with processed input and type

    Returns:
        ReformulateResponse with reformulated query and improvements
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    logger.info(
        "Reformulating query",
        context={
            "input_type": request.input_type,
            "input_length": len(request.processed_input),
            "use_llm": Config.REFORMULATION.USE_LLM,
        },
        request_id=request_id,
    )

    if not Config.REFORMULATION.USE_LLM:
        # Skip LLM reformulation, return input as-is
        logger.info(
            "LLM reformulation disabled, returning input as-is",
            request_id=request_id,
        )
        return ReformulateResponse(
            reformulated_query=request.processed_input,
            original_input=request.processed_input,
            improvements_made=["none (LLM reformulation disabled)"],
        )

    # Call Small LLM to reformulate the query
    try:
        reformulated, improvements = await _call_llm_for_reformulation(
            request.processed_input, request.input_type, request_id
        )

        logger.info(
            "Query reformulated successfully",
            context={
                "reformulated_length": len(reformulated),
                "improvements_count": len(improvements),
                "improvements": improvements,
            },
            request_id=request_id,
        )

        return ReformulateResponse(
            reformulated_query=reformulated,
            original_input=request.processed_input,
            improvements_made=improvements,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to reformulate query",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Reformulation service error: {str(e)}",
        )


async def _call_llm_for_reformulation(
    processed_input: str, input_type: str, request_id: str
) -> tuple[str, list[str]]:
    """
    Call the Small LLM service to reformulate the query.

    Args:
        processed_input: The processed user input
        input_type: Type of input (text or image)
        request_id: Request ID for logging

    Returns:
        Tuple of (reformulated_query, improvements_made)
    """
    # Build a prompt that instructs the LLM to reformulate the question
    prompt = f"""You are a math question reformulator. Your task is to improve the clarity and precision of math questions.

Original question: "{processed_input}"

Please reformulate this question to:
1. Use standard mathematical notation (e.g., x^2 instead of "x squared")
2. Make the question clear and complete
3. Fix any grammar or structural issues
4. Ensure it's precise for mathematical problem-solving

Respond ONLY with the reformulated question. Do not add explanations, introductions, or any other text.

Reformulated question:"""

    # Prepare request to Small LLM using OpenAI chat completions format
    payload = {
        "model": Config.SMALL_LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
    }

    logger.info(
        "Calling Small LLM service for reformulation",
        context={
            "url": Config.SERVICES.SMALL_LLM_URL,
            "input_length": len(processed_input),
        },
        request_id=request_id,
    )

    req = Request(
        f"{Config.SERVICES.SMALL_LLM_URL}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Request-ID": request_id},
        method="POST",
    )

    try:
        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            reformulated = result["choices"][0]["message"]["content"].strip()

            logger.debug(
                "Small LLM service responded",
                context={"raw_response_length": len(reformulated)},
                request_id=request_id,
            )

            # Clean up the response
            reformulated = _clean_llm_response(reformulated)

            # If reformulation failed or is empty, return original
            if not reformulated or len(reformulated) < 3:
                logger.warning(
                    "Reformulation produced empty or invalid result, using original",
                    context={
                        "reformulated_length": len(reformulated) if reformulated else 0
                    },
                    request_id=request_id,
                )
                return processed_input, ["none (reformulation failed)"]

            # Analyze what improvements were made
            improvements = _detect_improvements(processed_input, reformulated)

            logger.info(
                "Small LLM reformulation complete",
                context={
                    "original_length": len(processed_input),
                    "reformulated_length": len(reformulated),
                    "improvements": improvements,
                },
                request_id=request_id,
            )

            return reformulated, improvements

    except Exception as e:
        # If LLM call fails, return original input
        logger.error(
            "Failed to call Small LLM service",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Failed to call Small LLM service: {str(e)}",
        )


def _clean_llm_response(response: str) -> str:
    """
    Clean the LLM response to extract only the reformulated question.

    Handles:
    - <think> tags from reasoning models
    - Extra labels like "Reformulated question:"
    - LaTeX notation
    - Quotes

    Args:
        response: Raw response from LLM

    Returns:
        Cleaned reformulated question
    """
    # Remove <think> blocks (DeepSeek-R1 style reasoning)
    if "<think>" in response:
        # Extract content after </think>
        parts = response.split("</think>")
        if len(parts) > 1:
            response = parts[1].strip()

    # Remove common prefixes
    prefixes = [
        "Reformulated question:",
        "Reformulated:",
        "Question:",
        "Answer:",
    ]
    for prefix in prefixes:
        if response.startswith(prefix):
            response = response[len(prefix) :].strip()

    # Remove quotes if present
    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]

    # Clean up LaTeX notation for display
    # Convert \( ... \) to plain text (simple approach)
    response = response.replace("\\(", "").replace("\\)", "")

    return response.strip()


def _detect_improvements(original: str, reformulated: str) -> list[str]:
    """
    Detect what improvements were made to the query.

    Args:
        original: Original input
        reformulated: Reformulated query

    Returns:
        List of improvements made
    """
    improvements = []

    # Check if notation was standardized (contains ^)
    if "^" in reformulated and "^" not in original:
        improvements.append("standardized mathematical notation")

    # Check if question was made more explicit
    if len(reformulated) > len(original) * 1.2:
        improvements.append("added clarity and completeness")

    # Check if question mark was added
    if "?" in reformulated and "?" not in original:
        improvements.append("completed question structure")

    # Check if capitalization was improved
    if reformulated[0].isupper() and not original[0].isupper():
        improvements.append("improved capitalization")

    # Generic improvement if we detected changes but no specific improvements
    if not improvements and original.lower() != reformulated.lower():
        improvements.append("improved question clarity")

    # If no improvements detected, note that
    if not improvements:
        improvements.append("minor refinements")

    return improvements
