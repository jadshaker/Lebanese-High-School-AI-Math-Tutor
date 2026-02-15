import json
import time
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi import Response
from openai import OpenAI
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

# Initialize OpenAI client pointing to the LLM backend's OpenAI-compatible endpoint
client = OpenAI(
    base_url=f"{Config.SERVICES.REFORMULATOR_LLM_URL}/v1",
    api_key=Config.REFORMULATOR_LLM_API_KEY,
    timeout=Config.LLM_TIMEOUT,
)


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
    """Health check endpoint that verifies LLM backend connectivity and model availability."""
    llm_reachable = False
    model_available = False
    try:
        req = Request(
            f"{Config.SERVICES.REFORMULATOR_LLM_URL}/v1/models",
            method="GET",
            headers={"Authorization": f"Bearer {Config.REFORMULATOR_LLM_API_KEY}"},
        )
        with urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
            llm_reachable = True
            models = result.get("data", [])
            model_available = any(
                model.get("id") == Config.REFORMULATOR_LLM_MODEL_NAME
                for model in models
            )
    except Exception:
        pass

    return {
        "status": "healthy" if llm_reachable and model_available else "degraded",
        "service": "reformulator",
        "llm_reachable": llm_reachable,
        "model_available": model_available,
        "configured_model": Config.REFORMULATOR_LLM_MODEL_NAME,
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
def reformulate_query(request: ReformulateRequest, fastapi_request: FastAPIRequest):
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

    has_context = bool(
        request.conversation_history and len(request.conversation_history) > 0
    )

    logger.info(
        "Reformulating query",
        context={
            "input_type": request.input_type,
            "input_length": len(request.processed_input),
            "use_llm": Config.REFORMULATION.USE_LLM,
            "has_conversation_context": has_context,
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

    # Summarize conversation context if provided
    conversation_context = ""
    if has_context and request.conversation_history is not None:
        conversation_context = _summarize_conversation_context(
            request.conversation_history, request_id
        )
        logger.info(
            f"Summarized conversation context ({len(conversation_context)} chars)",
            request_id=request_id,
        )

    # Call LLM to reformulate the query
    try:
        reformulated, improvements = _call_llm_for_reformulation(
            request.processed_input,
            request.input_type,
            request_id,
            conversation_context,
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


def _summarize_conversation_context(conversation_history: list, request_id: str) -> str:
    """
    Summarize conversation history into a brief context string.

    Args:
        conversation_history: List of ConversationMessage objects
        request_id: Request ID for logging

    Returns:
        Summarized context string
    """
    if not conversation_history:
        return ""

    # Take only the most recent messages
    recent_messages = conversation_history[-Config.REFORMULATION.MAX_CONTEXT_MESSAGES :]

    # Build context summary
    context_parts = []
    for msg in recent_messages:
        role_label = "Student" if msg.role == "user" else "Tutor"
        # Truncate long messages
        content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        context_parts.append(f"{role_label}: {content}")

    context_summary = "\n".join(context_parts)

    # Truncate if too long
    if len(context_summary) > Config.REFORMULATION.MAX_CONTEXT_LENGTH:
        context_summary = (
            context_summary[: Config.REFORMULATION.MAX_CONTEXT_LENGTH] + "..."
        )

    return context_summary


def _call_llm_for_reformulation(
    processed_input: str,
    input_type: str,
    request_id: str,
    conversation_context: str = "",
) -> tuple[str, list[str]]:
    """
    Call the LLM service to reformulate the query.

    Args:
        processed_input: The processed user input
        input_type: Type of input (text or image)
        request_id: Request ID for logging
        conversation_context: Summarized conversation context

    Returns:
        Tuple of (reformulated_query, improvements_made)
    """
    # Build a prompt that instructs the LLM to reformulate the question
    context_section = ""
    if conversation_context:
        context_section = f"""
Previous conversation context:
{conversation_context}

"""

    prompt = f"""You are a math tutor assistant. Your task is to interpret user input and reformulate it if needed.
{context_section}
User input: "{processed_input}"

Rules:
- If the input is a math question or math-related, reformulate it to:
  1. Use standard mathematical notation (e.g., x^2 instead of "x squared")
  2. Make the question clear and complete
  3. Fix any grammar or structural issues
  4. Ensure it's precise for mathematical problem-solving
  5. If there's conversation context, resolve any references (like "it", "that", "the same") to make the question standalone
- If the input is a greeting (e.g., "hello", "hi", "hey"), return it exactly as-is.
- If the input is a general non-math question or statement, return it exactly as-is.
- Do NOT invent a math problem when there is none.

Respond ONLY with the reformulated question or the original input. Do not add explanations, introductions, or any other text.

Output:"""

    logger.info(
        "Calling LLM service for reformulation",
        context={
            "url": Config.SERVICES.REFORMULATOR_LLM_URL,
            "input_length": len(processed_input),
        },
        request_id=request_id,
    )

    try:
        response = client.chat.completions.create(
            model=Config.REFORMULATOR_LLM_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            top_p=0.9,
        )
        reformulated = (response.choices[0].message.content or "").strip()

        logger.debug(
            "LLM service responded",
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
        had_context = bool(conversation_context)
        improvements = _detect_improvements(processed_input, reformulated, had_context)

        logger.info(
            "LLM reformulation complete",
            context={
                "original_length": len(processed_input),
                "reformulated_length": len(reformulated),
                "improvements": improvements,
            },
            request_id=request_id,
        )

        return reformulated, improvements

    except Exception as e:
        logger.error(
            "Failed to call LLM service",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Failed to call LLM service: {str(e)}",
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


def _detect_improvements(
    original: str, reformulated: str, had_context: bool = False
) -> list[str]:
    """
    Detect what improvements were made to the query.

    Args:
        original: Original input
        reformulated: Reformulated query
        had_context: Whether conversation context was used

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

    # Check for reference resolution (e.g., "it" → specific term)
    reference_words = ["it", "that", "this", "the same", "them"]
    original_lower = original.lower()
    if had_context and any(word in original_lower for word in reference_words):
        if not any(word in reformulated.lower() for word in reference_words):
            improvements.append("resolved contextual references")

    # Generic improvement if we detected changes but no specific improvements
    if not improvements and original.lower() != reformulated.lower():
        improvements.append("improved question clarity")

    # If no improvements detected, note that
    if not improvements:
        improvements.append("minor refinements")

    return improvements
