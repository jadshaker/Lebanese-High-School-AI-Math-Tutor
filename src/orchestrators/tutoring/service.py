import asyncio
import re
import time
from typing import Any, Optional

from src.clients.embedding import embedding_client
from src.clients.llm import fine_tuned_client, small_llm_client
from src.config import Config
from src.logging_utils import StructuredLogger
from src.metrics import (
    gateway_embedding_duration_seconds,
    gateway_errors_total,
    gateway_llm_calls_total,
    gateway_small_llm_duration_seconds,
)
from src.models.schemas import SessionPhase
from src.orchestrators.answer_retrieval.service import (
    _clean_llm_response,
    retrieve_answer,
)
from src.orchestrators.data_processing.service import process_user_input
from src.orchestrators.tutoring.prompts import (
    CORRECTION_PATTERNS,
    TUTORING_NODE_IDENTITY_SYSTEM_PROMPT,
    TUTORING_SYSTEM_PROMPT,
)
from src.services import event_bus
from src.services.session import service as session_service
from src.services.vector_cache import service as vector_cache

logger = StructuredLogger("gateway")


async def _check_tutoring_node_identity(
    user_response: str, candidates: list[dict], request_id: str
) -> dict | None:
    """Ask the small LLM if the student's response is identical to any cached response.

    Returns the matched node dict (with id, system_response, etc.) or None.
    """
    if not candidates:
        return None

    start_time = time.time()
    try:
        cached_list = ""
        for i, node in enumerate(candidates[:5], 1):
            cached_list += f"{i}. {node.get('user_input', '')}\n"

        messages = [
            {"role": "system", "content": TUTORING_NODE_IDENTITY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"New student response: {user_response}\n\nCached student responses:\n{cached_list}",
            },
        ]

        logger.info(
            "  → Small LLM (tutoring node identity check)", request_id=request_id
        )

        call_params: dict[str, Any] = {
            "model": Config.SMALL_LLM.MODEL_NAME,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 512,
        }

        result = await asyncio.to_thread(
            small_llm_client.chat.completions.create, **call_params  # type: ignore[arg-type]
        )

        response_text = _clean_llm_response(
            result.choices[0].message.content or ""
        ).strip()
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)
        gateway_llm_calls_total.labels(
            llm_service="small_llm_tutoring_node_identity"
        ).inc()

        logger.info(
            f"  ✓ Small LLM tutoring node identity ({duration:.1f}s): {response_text}",
            request_id=request_id,
        )

        match = re.search(r"\bMATCH\s+(\d+)\b", response_text, re.IGNORECASE)
        if match:
            try:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(candidates):
                    matched_node = candidates[idx]
                    logger.info(
                        f"Tutoring node identity match: cached node #{idx + 1}",
                        context={"node_id": matched_node.get("id", "")},
                        request_id=request_id,
                    )
                    return matched_node
            except (ValueError, IndexError):
                pass

        logger.info("No tutoring node identity match found", request_id=request_id)
        return None

    except Exception as e:
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)
        logger.warning(
            f"Tutoring node identity check failed ({duration:.1f}s): {str(e)} — treating as no match",
            request_id=request_id,
        )
        return None


def _detect_correction(text: str) -> bool:
    """Lightweight regex check for correction intent."""
    text_lower = text.lower().strip()
    for pattern in CORRECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


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


async def _generate_tutoring_response(
    question: str,
    answer: str,
    conversation_path: list[dict],
    user_response: str,
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

        system_prompt = _safe_fmt(
            TUTORING_SYSTEM_PROMPT,
            question=question,
            answer=answer,
            path_context=path_context,
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

        is_complete = depth >= Config.TUTORING.MAX_INTERACTION_DEPTH
        next_prompt = (
            None
            if is_complete
            else "Do you understand this step? Would you like me to explain further?"
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
        5. If cache miss → detect correction or generate with Fine-tuned Model
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

    # Step 2: Check for correction before anything else
    if _detect_correction(user_response):
        logger.info(
            "CORRECTION detected — re-running answer retrieval pipeline",
            context={"corrected_input": user_response[:100]},
            request_id=request_id,
        )

        processing_result = await process_user_input(user_response, request_id)
        corrected_query = processing_result["reformulated_query"]

        retrieval_result = await retrieve_answer(
            corrected_query, request_id, original_query=user_response
        )
        new_answer = retrieval_result["answer"]
        new_question_id = retrieval_result.get("question_id", "")

        session_service.reset_tutoring_state(session_id, request_id=request_id)

        session_service.update_session(
            session_id,
            phase=SessionPhase.TUTORING,
            original_query=user_response,
            reformulated_query=corrected_query,
            retrieved_answer=new_answer,
            retrieval_source=retrieval_result.get("source", ""),
            request_id=request_id,
        )

        if new_question_id:
            session_service.update_tutoring_state(
                session_id,
                question_id=new_question_id,
                request_id=request_id,
            )

        logger.info(
            "CORRECTION pipeline completed",
            context={
                "new_question_id": new_question_id,
                "answer_length": len(new_answer),
            },
            request_id=request_id,
        )

        # Emit correction event for graph reset
        await event_bus.publish(
            session_id,
            {"type": "correction", "question_id": new_question_id},
        )

        return {
            "tutor_message": f"Got it! Let me help you with the corrected question.\n\n{new_answer}",
            "is_complete": False,
            "next_prompt": "Do you understand this step? Would you like me to explain further?",
            "intent": "correction",
            "cache_hit": False,
        }

    # Step 3: Check if we can skip cache search (new branch optimization)
    if is_new_branch:
        logger.info(
            "Skipping cache search: is_new_branch=True (node has no cached children)",
            request_id=request_id,
        )
        # Go directly to generation (step 6)
        user_embedding = await _embed_text(user_response, request_id)
    else:
        # Step 3b: Embed user response
        user_embedding = await _embed_text(user_response, request_id)

        # Emit cache_search event
        await event_bus.publish(
            session_id,
            {
                "type": "cache_search",
                "question_id": question_id,
                "parent_id": current_node_id,
            },
        )

        # Step 4: Search cache for top-K candidate children
        try:
            logger.info(
                f"  → Vector Cache (search children candidates, parent={current_node_id})",
                request_id=request_id,
            )
            candidates = await vector_cache.search_children_candidates(
                question_id=question_id,
                parent_id=current_node_id,
                user_input_embedding=user_embedding,
                threshold=0.5,
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
            candidates = []

        # Step 5: LLM identity check on candidates
        if candidates:
            matched_node = await _check_tutoring_node_identity(
                user_response, candidates, request_id
            )

            if matched_node:
                new_node_id = matched_node["id"]
                tutor_response = matched_node["system_response"]
                new_depth = matched_node.get("depth", depth + 1)
                match_score = matched_node.get("score", 0)

                logger.info(
                    f"Tutoring cache HIT (LLM verified): node_id={new_node_id}",
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

    # Step 6: Cache miss (or skipped) — generate with Fine-tuned Model
    logger.info("Tutoring cache MISS: generating new response", request_id=request_id)

    # Emit cache_miss event (only if we actually searched, not if skipped)
    if not is_new_branch:
        await event_bus.publish(
            session_id,
            {"type": "cache_miss", "parent_id": current_node_id},
        )

    # Get conversation path for context
    conversation_path: list[dict] = []
    if current_node_id:
        path_result = await _get_conversation_path(
            question_id, current_node_id, request_id
        )
        conversation_path = path_result.get("path", [])

    # Generate response with Fine-tuned Model (no intent routing)
    tutoring_result = await _generate_tutoring_response(
        question=original_question,
        answer=original_answer,
        conversation_path=conversation_path,
        user_response=user_response,
        depth=depth + 1,
        request_id=request_id,
    )

    # Step 7: Save new interaction to cache
    new_node_id = await _save_tutoring_interaction(
        question_id=question_id,
        parent_node_id=current_node_id,
        user_input=user_response,
        user_embedding=user_embedding,
        system_response=tutoring_result["response"],
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
                "depth": depth + 1,
            },
        )

    # Step 8: Update session with new node (mark as new branch since we just created it)
    if new_node_id and not tutoring_result["is_complete"]:
        session_service.update_tutoring_state(
            session_id=session_id,
            current_node_id=new_node_id,
            question_id=question_id,
            depth=depth + 1,
            is_new_branch=True,
            request_id=request_id,
        )

        # Emit position_update event
        await event_bus.publish(
            session_id,
            {
                "type": "position_update",
                "current_node_id": new_node_id,
                "depth": depth + 1,
            },
        )

    logger.info(
        f"Tutoring Interaction: completed - complete={tutoring_result['is_complete']}, saved_node={new_node_id}",
        request_id=request_id,
    )

    return {
        "tutor_message": tutoring_result["response"],
        "is_complete": tutoring_result["is_complete"],
        "next_prompt": tutoring_result["next_prompt"],
        "intent": "generated",
        "cache_hit": False,
    }
