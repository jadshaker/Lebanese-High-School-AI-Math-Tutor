import asyncio
import time
from typing import Any, Optional

from src.clients.embedding import embedding_client
from src.clients.llm import fine_tuned_client
from src.config import Config
from src.logging_utils import StructuredLogger
from src.metrics import (
    gateway_embedding_duration_seconds,
    gateway_errors_total,
    gateway_llm_calls_total,
)
from src.orchestrators.tutoring.prompts import (
    TUTORING_AFFIRMATIVE_PROMPT,
    TUTORING_NEGATIVE_PROMPT,
    TUTORING_OFF_TOPIC_PROMPT,
    TUTORING_PARTIAL_PROMPT,
    TUTORING_QUESTION_PROMPT,
    TUTORING_SKIP_PROMPT,
)
from src.services.intent_classifier.service import classify_text
from src.services.session import service as session_service
from src.services.vector_cache import service as vector_cache

logger = StructuredLogger("gateway")


async def _classify_intent(text: str, context: str | None, request_id: str) -> dict:
    """Classify user intent using the intent classifier service."""
    start_time = time.time()
    try:
        logger.info("  → Intent Classifier", request_id=request_id)

        result = classify_text(text, context, request_id)

        duration = time.time() - start_time
        logger.info(
            f"  ✓ Intent Classifier ({duration:.1f}s): {result.intent.value} (confidence: {result.confidence:.2f})",
            request_id=request_id,
        )
        return {
            "intent": result.intent.value,
            "confidence": result.confidence,
            "method": result.method.value,
        }

    except Exception as e:
        duration = time.time() - start_time
        gateway_errors_total.labels(error_type="intent_classifier_error").inc()

        logger.error(
            f"Intent classification failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        return {"intent": "question", "confidence": 0.5, "method": "fallback"}


async def _embed_text(text: str, request_id: str) -> list[float]:
    """Embed text using the embedding client."""
    start_time = time.time()
    try:
        logger.info("  → Embedding Service (tutoring)", request_id=request_id)

        if not embedding_client:
            raise RuntimeError("Embedding client not configured")

        response = await asyncio.to_thread(
            embedding_client.embeddings.create,
            model=Config.EMBEDDING.MODEL,
            input=text,
            dimensions=Config.EMBEDDING.DIMENSIONS,
        )

        embedding = response.data[0].embedding
        duration = time.time() - start_time
        gateway_embedding_duration_seconds.observe(duration)

        logger.info(
            f"  ✓ Embedding Service ({duration:.1f}s): {len(embedding)}D",
            request_id=request_id,
        )
        return embedding

    except Exception as e:
        duration = time.time() - start_time
        gateway_errors_total.labels(error_type="embedding_error").inc()
        logger.error(
            f"Embedding failed ({duration:.1f}s): {str(e)}", request_id=request_id
        )
        raise


async def _search_tutoring_cache(
    question_id: str,
    parent_node_id: Optional[str],
    user_embedding: list[float],
    request_id: str,
) -> dict:
    """Search for cached tutoring response among children of current node."""
    start_time = time.time()
    try:
        logger.info(
            f"  → Vector Cache (search children, parent={parent_node_id})",
            request_id=request_id,
        )

        result = await vector_cache.search_children(
            question_id=question_id,
            parent_id=parent_node_id,
            user_input_embedding=user_embedding,
            threshold=Config.TUTORING.CACHE_THRESHOLD,
            request_id=request_id,
        )

        duration = time.time() - start_time
        is_hit = result.get("is_cache_hit", False)
        score = result.get("match_score")

        logger.info(
            f"  ✓ Vector Cache search ({duration:.2f}s): hit={is_hit}, score={score}",
            request_id=request_id,
        )
        return result

    except Exception as e:
        duration = time.time() - start_time
        logger.warning(
            f"Tutoring cache search failed ({duration:.2f}s): {str(e)} (non-critical)",
            request_id=request_id,
        )
        return {"is_cache_hit": False, "match_score": None, "matched_node": None}


async def _save_tutoring_interaction(
    question_id: str,
    parent_node_id: Optional[str],
    user_input: str,
    user_embedding: list[float],
    system_response: str,
    request_id: str,
) -> str:
    """Save new tutoring interaction to cache as a child node."""
    start_time = time.time()
    try:
        logger.info("  → Vector Cache (save interaction)", request_id=request_id)

        node_id = await vector_cache.add_interaction(
            question_id=question_id,
            parent_id=parent_node_id,
            user_input=user_input,
            user_input_embedding=user_embedding,
            system_response=system_response,
            request_id=request_id,
        )

        duration = time.time() - start_time

        logger.info(
            f"  ✓ Vector Cache save ({duration:.2f}s): node_id={node_id}",
            request_id=request_id,
        )
        return node_id

    except Exception as e:
        duration = time.time() - start_time
        logger.warning(
            f"Tutoring cache save failed ({duration:.2f}s): {str(e)} (non-critical)",
            request_id=request_id,
        )
        return ""


async def _get_conversation_path(
    question_id: str, node_id: Optional[str], request_id: str
) -> dict:
    """Get the full conversation path from question to current node."""
    try:
        result = await vector_cache.get_conversation_path(question_id, node_id)
        return result
    except Exception:
        return {"path": [], "question_text": "", "answer_text": ""}


async def _generate_tutoring_response(
    question: str,
    answer: str,
    conversation_path: list[dict],
    user_response: str,
    intent: str,
    depth: int,
    request_id: str,
) -> dict:
    """Generate tutoring response using Fine-tuned Model with full context."""
    start_time = time.time()
    try:
        # Build conversation context from path
        path_context = ""
        if conversation_path:
            path_context = "\n\nPrevious tutoring steps:\n"
            for i, step in enumerate(conversation_path, 1):
                path_context += f"Step {i}:\n"
                path_context += f"  Student: {step.get('user_input', '')}\n"
                path_context += f"  Tutor: {step.get('system_response', '')}\n"

        def _safe_fmt(template: str, **kwargs: str) -> str:
            """Substitute {key} placeholders without crashing on user content with braces."""
            result = template
            for key, value in kwargs.items():
                result = result.replace(f"{{{key}}}", value)
            return result

        # Build prompt based on intent
        if intent == "skip":
            system_prompt = _safe_fmt(
                TUTORING_SKIP_PROMPT, question=question, answer=answer
            )
            user_prompt = "Give me the answer directly."
            is_complete = True

        elif intent == "affirmative":
            system_prompt = _safe_fmt(
                TUTORING_AFFIRMATIVE_PROMPT,
                question=question,
                answer=answer,
                path_context=path_context,
            )
            user_prompt = f"Student says: {user_response}"
            is_complete = depth >= Config.TUTORING.MAX_INTERACTION_DEPTH

        elif intent == "negative":
            system_prompt = _safe_fmt(
                TUTORING_NEGATIVE_PROMPT,
                question=question,
                answer=answer,
                path_context=path_context,
            )
            user_prompt = f"Student says they don't understand: {user_response}"
            is_complete = False

        elif intent == "partial":
            system_prompt = _safe_fmt(
                TUTORING_PARTIAL_PROMPT,
                question=question,
                answer=answer,
                path_context=path_context,
            )
            user_prompt = f"Student partially understands: {user_response}"
            is_complete = False

        elif intent == "question":
            system_prompt = _safe_fmt(
                TUTORING_QUESTION_PROMPT,
                question=question,
                answer=answer,
                path_context=path_context,
            )
            user_prompt = f"Student asks: {user_response}"
            is_complete = False

        else:  # off_topic
            system_prompt = _safe_fmt(
                TUTORING_OFF_TOPIC_PROMPT,
                question=question,
                path_context=path_context,
            )
            user_prompt = f"Student says: {user_response}"
            is_complete = False

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            f"  → Fine-Tuned Model (tutoring, intent={intent})", request_id=request_id
        )

        # Use fine_tuned_client directly instead of HTTP call
        call_params: dict[str, Any] = {
            "model": Config.FINE_TUNED_MODEL.MODEL_NAME,
            "messages": messages,
            "temperature": Config.FINE_TUNED_MODEL.TEMPERATURE,
            "top_p": Config.FINE_TUNED_MODEL.TOP_P,
        }
        if Config.FINE_TUNED_MODEL.MAX_TOKENS is not None:
            call_params["max_tokens"] = Config.FINE_TUNED_MODEL.MAX_TOKENS

        result = await asyncio.to_thread(
            fine_tuned_client.chat.completions.create, **call_params  # type: ignore[arg-type]
        )

        response = result.choices[0].message.content or ""
        duration = time.time() - start_time
        gateway_llm_calls_total.labels(llm_service="fine_tuned_tutoring").inc()

        # Clean <think> tags
        if "</think>" in response:
            response = response.split("</think>")[-1].strip()
        elif "<think>" in response:
            response = response.split("<think>")[0].strip()

        logger.info(
            f"  ✓ Fine-Tuned Model tutoring ({duration:.1f}s): {len(response)} chars",
            request_id=request_id,
        )

        next_prompt = None
        if not is_complete:
            next_prompt = (
                "Do you understand this step? Would you like me to explain further?"
            )

        return {
            "response": response,
            "is_complete": is_complete,
            "next_prompt": next_prompt,
        }

    except Exception as e:
        duration = time.time() - start_time
        gateway_errors_total.labels(error_type="tutoring_llm_error").inc()

        logger.error(
            f"Fine-Tuned Model tutoring failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def handle_tutoring_interaction(
    session_id: str,
    original_question: str,
    original_answer: str,
    question_id: str,
    user_response: str,
    request_id: str,
) -> dict:
    """
    Handle a tutoring interaction with full graph cache support.

    Flow:
        1. Get or create session (with question_id tracking)
        2. Embed user response
        3. Search cache for matching child of current node
        4. If cache hit → return cached response
        5. If cache miss → classify intent, generate with Fine-tuned Model
        6. Save new interaction to cache as child node
        7. Update session with new node ID
        8. Return response

    Args:
        session_id: Session ID for stateful conversation
        original_question: The original math question
        original_answer: The final answer (for context)
        question_id: The question's ID in the cache
        user_response: Student's response
        request_id: Request ID for tracing

    Returns:
        Dict with tutor_message, is_complete, next_prompt, intent, cache_hit
    """
    logger.info(
        f"Tutoring Interaction: session={session_id}, question_id={question_id}",
        request_id=request_id,
    )

    if not Config.TUTORING.ENABLE_TUTORING_MODE:
        logger.warning("Tutoring mode is disabled", request_id=request_id)
        return {
            "tutor_message": "Tutoring mode is currently disabled.",
            "is_complete": True,
            "next_prompt": None,
            "intent": "skip",
            "cache_hit": False,
        }

    # Step 1: Get or create session
    session = session_service.get_session(session_id)
    is_new_branch = False
    if session is None:
        session = session_service.create_session(
            initial_query=original_question, request_id=request_id
        )
        session_service.update_tutoring_state(
            session.session_id, question_id=question_id, request_id=request_id
        )
        current_node_id = None
        depth = 0
    else:
        current_node_id = session.tutoring.current_node_id
        depth = session.tutoring.depth
        is_new_branch = session.tutoring.is_new_branch

    # Step 2: Check if we can skip cache search (new branch optimization)
    if is_new_branch:
        logger.info(
            "Skipping cache search: is_new_branch=True (node has no cached children)",
            request_id=request_id,
        )
        # Go directly to intent classification + generation (step 5)
        user_embedding = await _embed_text(user_response, request_id)
    else:
        # Step 2b: Embed user response
        user_embedding = await _embed_text(user_response, request_id)

        # Step 3: Search cache for matching child node
        cache_result = await _search_tutoring_cache(
            question_id=question_id,
            parent_node_id=current_node_id,
            user_embedding=user_embedding,
            request_id=request_id,
        )

        # Step 4: Check for cache hit
        if cache_result.get("is_cache_hit") and cache_result.get("matched_node"):
            matched_node = cache_result["matched_node"]
            new_node_id = matched_node["id"]
            tutor_response = matched_node["system_response"]
            new_depth = matched_node.get("depth", depth + 1)

            logger.info(
                f"Tutoring cache HIT: node_id={new_node_id}, score={cache_result['match_score']:.2f}",
                request_id=request_id,
            )

            # Update session with the matched node (following existing path)
            session_service.update_tutoring_state(
                session_id=session_id,
                current_node_id=new_node_id,
                question_id=question_id,
                depth=new_depth,
                is_new_branch=False,
                request_id=request_id,
            )

            is_complete = new_depth >= Config.TUTORING.MAX_INTERACTION_DEPTH
            next_prompt = (
                None
                if is_complete
                else "Do you understand? Would you like me to explain further?"
            )

            return {
                "tutor_message": tutor_response,
                "is_complete": is_complete,
                "next_prompt": next_prompt,
                "intent": "cached",
                "cache_hit": True,
            }

    # Step 5: Cache miss (or skipped) - classify intent
    logger.info("Tutoring cache MISS: generating new response", request_id=request_id)

    context = f"The tutor is teaching: {original_question}"
    intent_result = await _classify_intent(user_response, context, request_id)
    intent = intent_result["intent"]

    # Step 6: Get conversation path for context
    conversation_path: list[dict] = []
    if current_node_id:
        path_result = await _get_conversation_path(
            question_id, current_node_id, request_id
        )
        conversation_path = path_result.get("path", [])

    # Step 7: Generate response with Fine-tuned Model
    tutoring_result = await _generate_tutoring_response(
        question=original_question,
        answer=original_answer,
        conversation_path=conversation_path,
        user_response=user_response,
        intent=intent,
        depth=depth + 1,
        request_id=request_id,
    )

    # Step 8: Save new interaction to cache
    new_node_id = await _save_tutoring_interaction(
        question_id=question_id,
        parent_node_id=current_node_id,
        user_input=user_response,
        user_embedding=user_embedding,
        system_response=tutoring_result["response"],
        request_id=request_id,
    )

    # Step 9: Update session with new node (mark as new branch since we just created it)
    if new_node_id and not tutoring_result["is_complete"]:
        session_service.update_tutoring_state(
            session_id=session_id,
            current_node_id=new_node_id,
            question_id=question_id,
            depth=depth + 1,
            is_new_branch=True,
            request_id=request_id,
        )

    logger.info(
        f"Tutoring Interaction: completed - intent={intent}, complete={tutoring_result['is_complete']}, saved_node={new_node_id}",
        request_id=request_id,
    )

    return {
        "tutor_message": tutoring_result["response"],
        "is_complete": tutoring_result["is_complete"],
        "next_prompt": tutoring_result["next_prompt"],
        "intent": intent,
        "cache_hit": False,
    }
