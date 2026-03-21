import asyncio
import re
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
from src.models.schemas import SessionPhase
from src.orchestrators.answer_retrieval.service import (
    _clean_llm_response,
    retrieve_answer,
)
from src.orchestrators.data_processing.service import process_user_input
from src.orchestrators.tutoring.prompts import TUTORING_SYSTEM_PROMPT
from src.services import event_bus
from src.services.session import service as session_service
from src.services.vector_cache import service as vector_cache

logger = StructuredLogger("gateway")


def _safe_fmt(template: str, **kwargs: str) -> str:
    """Substitute $key$ placeholders safely — avoids collisions with math braces."""
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"${key}$", value)
    return result


def _parse_tutoring_response(
    response_text: str, candidates: list[dict]
) -> tuple[str, str | None, dict | None]:
    """Parse the Fine-tuned model response to detect routing signals.

    Returns (classification, response_text_or_none, matched_node_or_none):
        - ("match", None, matched_node) — identical to a cached response
        - ("new_question", None, None) — new math question or correction
        - ("tutoring", response_text, None) — direct tutoring response
    """
    stripped = response_text.strip()

    # Check for [MATCH:<number>]
    match = re.search(r"\[MATCH:(\d+)\]", stripped)
    if match and candidates:
        try:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(candidates):
                return ("match", None, candidates[idx])
        except (ValueError, IndexError):
            pass

    # Check for [NEW_QUESTION]
    if "[NEW_QUESTION]" in stripped:
        return ("new_question", None, None)

    # Everything else is a direct tutoring response
    return ("tutoring", response_text, None)


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


async def _call_fine_tuned(
    question: str,
    answer: str,
    conversation_path: list[dict],
    candidates: list[dict],
    user_response: str,
    request_id: str,
) -> tuple[str, str | None, dict | None]:
    """Single Fine-tuned model call that classifies AND generates.

    Returns (classification, response_or_none, matched_node_or_none):
        - ("match", None, matched_node) — use cached response
        - ("new_question", None, None) — route to Q&A pipeline
        - ("tutoring", response_text, None) — direct tutoring response
    """
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

        # Build candidates section
        candidates_section = ""
        if candidates:
            candidates_section = "\n**Cached student responses** (check for match before responding):\n"
            for i, node in enumerate(candidates[:5], 1):
                candidates_section += f"{i}. {node.get('user_input', '')}\n"

        system_prompt = _safe_fmt(
            TUTORING_SYSTEM_PROMPT,
            question=question,
            answer=answer,
            path_context=path_context,
            candidates_section=candidates_section,
            user_response=user_response,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_response},
        ]

        logger.info("  → Fine-Tuned Model (tutoring)", request_id=request_id)

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

        response = _clean_llm_response(result.choices[0].message.content or "")
        duration = time.time() - start_time
        gateway_llm_calls_total.labels(llm_service="fine_tuned_tutoring").inc()

        logger.info(
            f"  ✓ Fine-Tuned Model tutoring ({duration:.1f}s): {len(response)} chars",
            request_id=request_id,
        )

        classification, text, matched = _parse_tutoring_response(response, candidates)

        logger.info(
            f"  Tutoring classification: {classification}",
            context={
                "matched_node": matched.get("id", "") if matched else None,
            },
            request_id=request_id,
        )

        return classification, text, matched

    except Exception as e:
        duration = time.time() - start_time
        gateway_errors_total.labels(error_type="tutoring_llm_error").inc()

        logger.error(
            f"Fine-Tuned Model tutoring failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def _handle_new_question(
    session_id: str,
    user_response: str,
    request_id: str,
) -> dict:
    """Handle NEW_QUESTION classification: run full Q&A pipeline and reset session.

    This covers both new questions and corrections of the original question.
    """
    logger.info(
        "NEW_QUESTION detected — running full Q&A pipeline",
        context={"input": user_response[:100]},
        request_id=request_id,
    )

    # Step 1: Process + reformulate
    processing_result = await process_user_input(user_response, request_id)
    reformulated_query = processing_result["reformulated_query"]

    # Step 2: Answer retrieval (embed → search → identity check → generate if miss)
    retrieval_result = await retrieve_answer(
        reformulated_query, request_id, original_query=user_response
    )
    new_answer = retrieval_result["answer"]
    new_question_id = retrieval_result.get("question_id", "")

    # Step 3: Reset session tutoring state
    await session_service.reset_tutoring_state(session_id, request_id=request_id)

    # Step 4: Update session with new question context
    await session_service.update_session(
        session_id,
        phase=SessionPhase.TUTORING,
        original_query=user_response,
        reformulated_query=reformulated_query,
        retrieved_answer=new_answer,
        retrieval_source=retrieval_result.get("source", ""),
        request_id=request_id,
    )

    if new_question_id:
        await session_service.update_tutoring_state(
            session_id,
            question_id=new_question_id,
            request_id=request_id,
        )

    logger.info(
        "NEW_QUESTION pipeline completed",
        context={
            "new_question_id": new_question_id,
            "answer_length": len(new_answer),
        },
        request_id=request_id,
    )

    # Emit new_question event for graph visualization
    await event_bus.publish(
        session_id,
        {"type": "new_question", "question_id": new_question_id},
    )

    return {
        "tutor_message": new_answer,
        "is_complete": False,
        "next_prompt": "Do you understand this step? Would you like me to explain further?",
        "intent": "new_question",
        "cache_hit": False,
    }


async def handle_tutoring_interaction(
    session_id: str,
    original_question: str,
    original_answer: str,
    question_id: str,
    user_response: str,
    request_id: str,
) -> dict:
    """Handle a tutoring interaction with full graph cache support.

    Flow:
        1. Get or create session (with question_id tracking)
        2. Embed user response
        3. Search cache for candidate children of current node (skip if is_new_branch)
        4. Single Fine-tuned model call: classify + generate
           - [MATCH:<n>] → return cached response
           - [NEW_QUESTION] → run full Q&A pipeline (Large LLM)
           - otherwise → use the response directly as tutoring output
        5. Save new tutoring interaction to cache
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
    session = await session_service.get_session(session_id)
    is_new_branch = False
    if session is None:
        session = await session_service.create_session(
            initial_query=original_question, request_id=request_id
        )
        await session_service.update_tutoring_state(
            session.session_id, question_id=question_id, request_id=request_id
        )
        current_node_id = None
        depth = 0
    else:
        current_node_id = session.tutoring.current_node_id
        depth = session.tutoring.depth
        is_new_branch = session.tutoring.is_new_branch

    # Emit session_start event for graph visualization
    await event_bus.publish(
        session_id,
        {
            "type": "session_start",
            "question_id": question_id,
            "current_node_id": current_node_id,
            "depth": depth,
        },
    )

    # Step 2: Embed user response
    user_embedding = await _embed_text(user_response, request_id)

    # Step 3: Search cache for candidate children (skip if new branch)
    candidates: list[dict] = []
    if is_new_branch:
        logger.info(
            "Skipping cache search: is_new_branch=True (node has no cached children)",
            request_id=request_id,
        )
    else:
        # Emit cache_search event
        await event_bus.publish(
            session_id,
            {
                "type": "cache_search",
                "question_id": question_id,
                "parent_id": current_node_id,
            },
        )

        try:
            logger.info(
                f"  → Vector Cache (search children candidates, parent={current_node_id})",
                request_id=request_id,
            )
            candidates = await vector_cache.search_children_candidates(
                question_id=question_id,
                parent_id=current_node_id,
                user_input_embedding=user_embedding,
                threshold=0.8,
                top_k=5,
                request_id=request_id,
            )
            logger.info(
                f"  ✓ Vector Cache search: {len(candidates)} candidates found",
                request_id=request_id,
            )
        except Exception as e:
            logger.warning(
                f"Tutoring cache search failed: {str(e)} (non-critical)",
                request_id=request_id,
            )

    # Step 4: Get conversation path for context
    conversation_path: list[dict] = []
    if current_node_id:
        path_result = await _get_conversation_path(
            question_id, current_node_id, request_id
        )
        conversation_path = path_result.get("path", [])

    # Step 5: Single Fine-tuned model call — classify + generate
    classification, tutor_response, matched_node = await _call_fine_tuned(
        question=original_question,
        answer=original_answer,
        conversation_path=conversation_path,
        candidates=candidates,
        user_response=user_response,
        request_id=request_id,
    )

    # === Handle MATCH — return cached response ===
    if classification == "match" and matched_node:
        new_node_id = matched_node["id"]
        cached_response = matched_node["system_response"]
        new_depth = matched_node.get("depth", depth + 1)
        match_score = matched_node.get("score", 0)

        logger.info(
            f"Tutoring cache HIT: node_id={new_node_id}",
            request_id=request_id,
        )

        # Emit cache_hit and position_update events
        await event_bus.publish(
            session_id,
            {
                "type": "cache_hit",
                "matched_node_id": new_node_id,
                "score": match_score,
            },
        )
        await event_bus.publish(
            session_id,
            {
                "type": "position_update",
                "current_node_id": new_node_id,
                "depth": new_depth,
            },
        )

        # Update session with the matched node (following existing path)
        await session_service.update_tutoring_state(
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
            "tutor_message": cached_response,
            "is_complete": is_complete,
            "next_prompt": next_prompt,
            "intent": "cached",
            "cache_hit": True,
        }

    # === Handle NEW_QUESTION — run full Q&A pipeline ===
    if classification == "new_question":
        return await _handle_new_question(
            session_id=session_id,
            user_response=user_response,
            request_id=request_id,
        )

    # === Handle TUTORING — use the generated response directly ===
    assert tutor_response is not None
    new_depth = depth + 1

    logger.info("Tutoring response generated", request_id=request_id)

    # Emit cache_miss event (only if we actually searched)
    if not is_new_branch:
        await event_bus.publish(
            session_id,
            {"type": "cache_miss", "parent_id": current_node_id},
        )

    # Save new interaction to cache
    new_node_id = await _save_tutoring_interaction(
        question_id=question_id,
        parent_node_id=current_node_id,
        user_input=user_response,
        user_embedding=user_embedding,
        system_response=tutor_response,
        request_id=request_id,
    )

    # Emit node_created event
    if new_node_id:
        await event_bus.publish(
            session_id,
            {
                "type": "node_created",
                "node_id": new_node_id,
                "parent_id": current_node_id,
                "question_id": question_id,
                "user_input": user_response,
                "depth": new_depth,
            },
        )

    is_complete = new_depth >= Config.TUTORING.MAX_INTERACTION_DEPTH
    next_prompt = (
        None
        if is_complete
        else "Do you understand this step? Would you like me to explain further?"
    )

    # Update session with new node (mark as new branch since we just created it)
    if new_node_id and not is_complete:
        await session_service.update_tutoring_state(
            session_id=session_id,
            current_node_id=new_node_id,
            question_id=question_id,
            depth=new_depth,
            is_new_branch=True,
            request_id=request_id,
        )

        # Emit position_update event
        await event_bus.publish(
            session_id,
            {
                "type": "position_update",
                "current_node_id": new_node_id,
                "depth": new_depth,
            },
        )

    logger.info(
        f"Tutoring Interaction: completed - complete={is_complete}, saved_node={new_node_id}",
        request_id=request_id,
    )

    return {
        "tutor_message": tutor_response,
        "is_complete": is_complete,
        "next_prompt": next_prompt,
        "intent": "generated",
        "cache_hit": False,
    }
