import json
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from src.config import Config
from src.models.schemas import ReformulateRequest, ReformulateResponse

app = FastAPI(title="Math Tutor Reformulator Service")


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


@app.post("/reformulate", response_model=ReformulateResponse)
async def reformulate_query(request: ReformulateRequest):
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
    if not Config.REFORMULATION.USE_LLM:
        # Skip LLM reformulation, return input as-is
        return ReformulateResponse(
            reformulated_query=request.processed_input,
            original_input=request.processed_input,
            improvements_made=["none (LLM reformulation disabled)"],
        )

    # Call Small LLM to reformulate the query
    try:
        reformulated, improvements = await _call_llm_for_reformulation(
            request.processed_input, request.input_type
        )

        return ReformulateResponse(
            reformulated_query=reformulated,
            original_input=request.processed_input,
            improvements_made=improvements,
        )

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Reformulation service error: {str(e)}",
        )


async def _call_llm_for_reformulation(
    processed_input: str, input_type: str
) -> tuple[str, list[str]]:
    """
    Call the Small LLM service to reformulate the query.

    Args:
        processed_input: The processed user input
        input_type: Type of input (text or image)

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
        "model": "deepseek-r1:7b",
        "messages": [{"role": "user", "content": prompt}],
    }

    req = Request(
        f"{Config.SERVICES.SMALL_LLM_URL}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            reformulated = result["choices"][0]["message"]["content"].strip()

            # Clean up the response
            reformulated = _clean_llm_response(reformulated)

            # If reformulation failed or is empty, return original
            if not reformulated or len(reformulated) < 3:
                return processed_input, ["none (reformulation failed)"]

            # Analyze what improvements were made
            improvements = _detect_improvements(processed_input, reformulated)

            return reformulated, improvements

    except Exception as e:
        # If LLM call fails, return original input
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
