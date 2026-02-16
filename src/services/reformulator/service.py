from fastapi import HTTPException

from src.clients.llm import reformulator_client
from src.config import Config
from src.logging_utils import StructuredLogger
from src.models.schemas import ReformulateResponse
from src.services.reformulator.prompts import REFORMULATION_PROMPT

logger = StructuredLogger("reformulator")


def reformulate_query(
    processed_input: str,
    input_type: str,
    request_id: str,
    conversation_history: list | None = None,
) -> ReformulateResponse:
    """Reformulate user input to improve clarity and precision."""
    has_context = bool(conversation_history and len(conversation_history) > 0)

    logger.info(
        "Reformulating query",
        context={
            "input_type": input_type,
            "input_length": len(processed_input),
            "use_llm": Config.REFORMULATION.USE_LLM,
            "has_conversation_context": has_context,
        },
        request_id=request_id,
    )

    if not Config.REFORMULATION.USE_LLM:
        logger.info(
            "LLM reformulation disabled, returning input as-is",
            request_id=request_id,
        )
        return ReformulateResponse(
            reformulated_query=processed_input,
            original_input=processed_input,
            improvements_made=["none (LLM reformulation disabled)"],
        )

    # Summarize conversation context if provided
    conversation_context = ""
    if has_context and conversation_history is not None:
        conversation_context = _summarize_conversation_context(
            conversation_history, request_id
        )

    # Call LLM to reformulate
    reformulated, improvements = _call_llm_for_reformulation(
        processed_input, input_type, request_id, conversation_context
    )

    logger.info(
        "Query reformulated successfully",
        context={
            "reformulated_length": len(reformulated),
            "improvements_count": len(improvements),
        },
        request_id=request_id,
    )

    return ReformulateResponse(
        reformulated_query=reformulated,
        original_input=processed_input,
        improvements_made=improvements,
    )


def _summarize_conversation_context(conversation_history: list, request_id: str) -> str:
    """Summarize conversation history into a brief context string."""
    if not conversation_history:
        return ""

    recent_messages = conversation_history[-Config.REFORMULATION.MAX_CONTEXT_MESSAGES :]

    context_parts = []
    for msg in recent_messages:
        role_label = "Student" if msg.role == "user" else "Tutor"
        content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        context_parts.append(f"{role_label}: {content}")

    context_summary = "\n".join(context_parts)

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
    """Call the LLM to reformulate the query."""
    context_section = ""
    if conversation_context:
        context_section = f"\nPrevious conversation context:\n{conversation_context}\n"

    prompt = REFORMULATION_PROMPT.format(
        context_section=context_section,
        processed_input=processed_input,
    )

    try:
        response = reformulator_client.chat.completions.create(
            model=Config.REFORMULATOR_LLM.MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=Config.REFORMULATOR_LLM.TEMPERATURE,
            top_p=Config.REFORMULATOR_LLM.TOP_P,
            max_tokens=Config.REFORMULATOR_LLM.MAX_TOKENS,
        )
        reformulated = (response.choices[0].message.content or "").strip()

        # Clean up the response
        reformulated = _clean_llm_response(reformulated)

        if not reformulated or len(reformulated) < 3:
            return processed_input, ["none (reformulation failed)"]

        had_context = bool(conversation_context)
        improvements = _detect_improvements(processed_input, reformulated, had_context)

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
    """Clean the LLM response to extract only the reformulated question."""
    if "</think>" in response:
        response = response.split("</think>")[-1].strip()
    elif "<think>" in response:
        response = response.split("<think>")[0].strip()

    prefixes = [
        "Reformulated question:",
        "Reformulated:",
        "Question:",
        "Answer:",
    ]
    for prefix in prefixes:
        if response.startswith(prefix):
            response = response[len(prefix) :].strip()

    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]

    response = response.replace("\\(", "").replace("\\)", "")
    return response.strip()


def _detect_improvements(
    original: str, reformulated: str, had_context: bool = False
) -> list[str]:
    """Detect what improvements were made to the query."""
    improvements = []

    if "^" in reformulated and "^" not in original:
        improvements.append("standardized mathematical notation")

    if len(reformulated) > len(original) * 1.2:
        improvements.append("added clarity and completeness")

    if "?" in reformulated and "?" not in original:
        improvements.append("completed question structure")

    if reformulated[0].isupper() and not original[0].isupper():
        improvements.append("improved capitalization")

    reference_words = ["it", "that", "this", "the same", "them"]
    original_lower = original.lower()
    if had_context and any(word in original_lower for word in reference_words):
        if not any(word in reformulated.lower() for word in reference_words):
            improvements.append("resolved contextual references")

    if not improvements and original.lower() != reformulated.lower():
        improvements.append("improved question clarity")

    if not improvements:
        improvements.append("minor refinements")

    return improvements
