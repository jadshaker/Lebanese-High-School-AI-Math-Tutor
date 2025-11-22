import json
import re
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from openai import OpenAI
from src.config import Config
from src.models.schemas import ReformulatorRequest, ReformulatorResponse

app = FastAPI(title="Reformulator Service", version="1.0.0")

client = OpenAI(
    base_url=f"{Config.OLLAMA_SERVICE_URL}/v1",
    api_key="ollama",
)


@app.get("/health")
def health_check() -> dict[str, str | bool]:
    """Health check endpoint that verifies Ollama connectivity and model availability."""
    ollama_reachable = False
    model_available = False

    try:
        req = Request(
            f"{Config.OLLAMA_SERVICE_URL}/api/tags",
            method="GET",
        )

        with urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
            ollama_reachable = True

            models = result.get("models", [])
            model_available = any(
                model.get("name") == Config.OLLAMA_MODEL_NAME for model in models
            )

    except Exception:
        pass

    return {
        "status": "healthy" if ollama_reachable and model_available else "degraded",
        "service": "reformulator",
        "ollama_reachable": ollama_reachable,
        "model_available": model_available,
        "configured_model": Config.OLLAMA_MODEL_NAME,
    }


@app.post("/reformulate", response_model=ReformulatorResponse)
def reformulate_query(request: ReformulatorRequest) -> ReformulatorResponse:
    """
    Reformulate a user query with context using a two-step LLM process.

    Step 1: Combine previous context + last reply into summarized context
    Step 2: Use summarized context + user query to produce structured output

    Args:
        request: ReformulatorRequest containing query, previous_context, and last_reply

    Returns:
        ReformulatorResponse with lesson, context, reformulated query, and location_in_chat

    Raises:
        HTTPException: If Ollama service is unavailable or returns an error
    """
    try:
        # STEP 1: Summarize context if we have previous context or last reply
        summarized_context = ""
        if request.previous_context or request.last_reply:
            context_input = f"Previous context: {request.previous_context}\n\nLast reply: {request.last_reply}"

            context_response = client.chat.completions.create(
                model=Config.OLLAMA_MODEL_NAME,
                messages=[
                    {"role": "system", "content": Config.CONTEXT_SUMMARIZATION_PROMPT},
                    {"role": "user", "content": context_input},
                ],
                extra_body={"keep_alive": -1},
            )

            summarized_context = (
                context_response.choices[0].message.content or ""
            ).strip()

        # STEP 2: Reformulate query with summarized context
        reformulation_input = f"Context: {summarized_context}\n\nUser query: {request.query}"

        reformulation_response = client.chat.completions.create(
            model=Config.OLLAMA_MODEL_NAME,
            messages=[
                {"role": "system", "content": Config.REFORMULATION_PROMPT},
                {"role": "user", "content": reformulation_input},
            ],
            extra_body={"keep_alive": -1},
        )

        raw_answer = reformulation_response.choices[0].message.content or ""

        # Extract JSON from the response (handles DeepSeek-R1's <think> tags and markdown)
        json_match = re.search(r"\{[^{}]*\"lesson\"[^{}]*\}", raw_answer, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                # Parse the JSON string into a Python dict
                reformulated = json.loads(json_str)

                return ReformulatorResponse(
                    lesson=reformulated.get("lesson", "General"),
                    context=reformulated.get("context", summarized_context),
                    query=reformulated.get("query", request.query),
                    location_in_chat=reformulated.get("location_in_chat", "start"),
                )
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to parse JSON from LLM response: {json_str}",
                )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"No valid JSON found in LLM response: {raw_answer[:200]}",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Reformulator service error: {str(e)}",
        )


@app.post("/reformulate/mock", response_model=ReformulatorResponse)
def mock_reformulate(request: ReformulatorRequest) -> ReformulatorResponse:
    """
    Mock endpoint for testing the reformulator without calling the LLM.

    Returns a predictable response based on the input query and context.

    Args:
        request: ReformulatorRequest containing query, previous_context, and last_reply

    Returns:
        ReformulatorResponse with mock data
    """
    # Determine location in chat
    location = "start"
    if request.previous_context or request.last_reply:
        location = "followup"

    # Create a mock summarized context
    context_parts = []
    if request.previous_context:
        context_parts.append(request.previous_context)
    if request.last_reply:
        context_parts.append(f"Assistant discussed: {request.last_reply[:50]}...")

    summarized_context = " ".join(context_parts) if context_parts else ""

    # Mock lesson detection (simple keyword matching)
    lesson = "General"
    query_lower = request.query.lower()
    if any(
        word in query_lower
        for word in ["vector", "vectors", "scalar", "projection", "plane"]
    ):
        lesson = "Addition of vectors"
    elif any(word in query_lower for word in ["derivative", "function", "limit"]):
        lesson = "Study of functions"
    elif any(word in query_lower for word in ["line", "slope", "equation"]):
        lesson = "Equations of straight lines"
    elif any(word in query_lower for word in ["triangle", "geometry", "angle"]):
        lesson = "Straight lines and planes"

    # Create reformulated query
    if summarized_context:
        reformulated_query = f"Given that {summarized_context}, {request.query}"
    else:
        reformulated_query = request.query

    return ReformulatorResponse(
        lesson=lesson,
        context=summarized_context,
        query=reformulated_query,
        location_in_chat=location,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8009)
