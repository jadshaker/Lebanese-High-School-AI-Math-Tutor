import time
from typing import Optional

from src.clients.http_client import call_service
from src.config import Config
from src.logging_utils import StructuredLogger
from src.metrics import (
    gateway_embedding_duration_seconds,
    gateway_errors_total,
    gateway_llm_calls_total,
)

logger = StructuredLogger("gateway")

# Threshold for tutoring cache hit
TUTORING_CACHE_THRESHOLD = 0.85


async def _classify_intent(
    text: str, context: str | None, request_id: str
) -> dict:
    """Classify user intent using the intent classifier service."""
    start_time = time.time()
    try:
        logger.info("  → Intent Classifier", request_id=request_id)

        result = await call_service(
            f"{Config.SERVICES.INTENT_CLASSIFIER_URL}/classify",
            {"text": text, "context": context},
            request_id,
            timeout=15,
        )

        duration = time.time() - start_time
        logger.info(
            f"  ✓ Intent Classifier ({duration:.1f}s): {result['intent']} (confidence: {result['confidence']:.2f})",
            request_id=request_id,
        )
        return result

    except Exception as e:
        duration = time.time() - start_time
        gateway_errors_total.labels(error_type="intent_classifier_error").inc()

        logger.error(
            f"Intent classification failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        return {"intent": "question", "confidence": 0.5, "method": "fallback"}


async def _embed_text(text: str, request_id: str) -> list[float]:
    """Embed text using the embedding service."""
    start_time = time.time()
    try:
        logger.info("  → Embedding Service (tutoring)", request_id=request_id)

        result = await call_service(
            f"{Config.SERVICES.EMBEDDING_URL}/embed",
            {"text": text},
            request_id,
            timeout=10,
        )

        duration = time.time() - start_time
        gateway_embedding_duration_seconds.observe(duration)

        logger.info(
            f"  ✓ Embedding Service ({duration:.1f}s): {len(result['embedding'])}D",
            request_id=request_id,
        )
        return result["embedding"]

    except Exception as e:
        duration = time.time() - start_time
        gateway_errors_total.labels(error_type="embedding_error").inc()
        logger.error(
            f"Embedding failed ({duration:.1f}s): {str(e)}", request_id=request_id
        )
        raise


async def _get_session(session_id: str, request_id: str) -> dict | None:
    """Get session state from session service."""
    try:
        result = await call_service(
            f"{Config.SERVICES.SESSION_URL}/sessions/{session_id}",
            None,
            request_id,
            timeout=5,
            method="GET",
        )
        return result
    except Exception:
        return None


async def _create_session(
    session_id: str, original_question: str, question_id: str, request_id: str
) -> dict:
    """Create a new tutoring session with question_id tracking."""
    result = await call_service(
        f"{Config.SERVICES.SESSION_URL}/sessions",
        {
            "session_id": session_id,
            "original_question": original_question,
            "question_id": question_id,
        },
        request_id,
        timeout=5,
    )
    return result


async def _update_tutoring_state(
    session_id: str,
    current_node_id: Optional[str],
    question_id: str,
    depth: int,
    request_id: str,
    is_new_branch: bool = False,
) -> dict:
    """Update tutoring state in session with actual node ID."""
    result = await call_service(
        f"{Config.SERVICES.SESSION_URL}/sessions/{session_id}/tutoring",
        {
            "current_node_id": current_node_id,
            "question_id": question_id,
            "depth": depth,
            "is_new_branch": is_new_branch,
        },
        request_id,
        timeout=5,
        method="PATCH",
    )
    return result


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

        result = await call_service(
            f"{Config.SERVICES.VECTOR_CACHE_URL}/interactions/search",
            {
                "question_id": question_id,
                "parent_id": parent_node_id,
                "user_input_embedding": user_embedding,
                "threshold": TUTORING_CACHE_THRESHOLD,
            },
            request_id,
            timeout=10,
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

        result = await call_service(
            f"{Config.SERVICES.VECTOR_CACHE_URL}/interactions",
            {
                "question_id": question_id,
                "parent_id": parent_node_id,
                "user_input": user_input,
                "user_input_embedding": user_embedding,
                "system_response": system_response,
            },
            request_id,
            timeout=10,
        )

        duration = time.time() - start_time
        node_id = result.get("id", "unknown")

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
        result = await call_service(
            f"{Config.SERVICES.VECTOR_CACHE_URL}/interactions/{node_id or 'root'}/path",
            {"question_id": question_id},
            request_id,
            timeout=10,
            method="GET",
        )
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

        # Build prompt based on intent
        if intent == "skip":
            system_prompt = f"""You are a math tutor for Lebanese high school students.
The student wants to skip the explanation and get the direct answer.

Original Question: {question}
Final Answer: {answer}

Provide the direct answer clearly."""
            user_prompt = "Give me the answer directly."
            is_complete = True

        elif intent == "affirmative":
            system_prompt = f"""You are a math tutor for Lebanese high school students.
The student understands the current step. Move to the next step or conclude.

Original Question: {question}
Final Answer: {answer}
{path_context}

Continue teaching, building on what the student now understands."""
            user_prompt = f"Student says: {user_response}"
            is_complete = depth >= Config.TUTORING.MAX_INTERACTION_DEPTH

        elif intent == "negative":
            system_prompt = f"""You are a math tutor for Lebanese high school students.
The student does not understand. Provide a simpler explanation.

Original Question: {question}
Final Answer: {answer}
{path_context}

Break down the concept further in simpler terms."""
            user_prompt = f"Student says they don't understand: {user_response}"
            is_complete = False

        elif intent == "partial":
            system_prompt = f"""You are a math tutor for Lebanese high school students.
The student partially understands. Clarify the confusing parts.

Original Question: {question}
Final Answer: {answer}
{path_context}

Build on what they know while clarifying confusion."""
            user_prompt = f"Student partially understands: {user_response}"
            is_complete = False

        elif intent == "question":
            system_prompt = f"""You are a math tutor for Lebanese high school students.
The student has a follow-up question. Answer it clearly.

Original Question: {question}
Final Answer: {answer}
{path_context}

Answer their specific question, then guide them back to the problem."""
            user_prompt = f"Student asks: {user_response}"
            is_complete = False

        else:  # off_topic
            system_prompt = f"""You are a math tutor for Lebanese high school students.
The student's response seems off-topic. Gently redirect them.

Original Question: {question}
{path_context}

Redirect them back to the math problem."""
            user_prompt = f"Student says: {user_response}"
            is_complete = False

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            f"  → Fine-Tuned Model (tutoring, intent={intent})", request_id=request_id
        )

        # Use Fine-tuned Model instead of Small LLM
        result = await call_service(
            f"{Config.SERVICES.FINE_TUNED_MODEL_URL}/v1/chat/completions",
            {"model": "tinyllama:latest", "messages": messages},
            request_id,
            timeout=60,
        )

        response = result["choices"][0]["message"]["content"]
        duration = time.time() - start_time
        gateway_llm_calls_total.labels(llm_service="fine_tuned_tutoring").inc()

        logger.info(
            f"  ✓ Fine-Tuned Model tutoring ({duration:.1f}s): {len(response)} chars",
            request_id=request_id,
        )

        next_prompt = None
        if not is_complete:
            next_prompt = "Do you understand this step? Would you like me to explain further?"

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
    session = await _get_session(session_id, request_id)
    is_new_branch = False
    if session is None:
        session = await _create_session(
            session_id, original_question, question_id, request_id
        )
        current_node_id = None
        depth = 0
    else:
        tutoring_state = session.get("tutoring", {})
        current_node_id = tutoring_state.get("current_node_id")
        depth = tutoring_state.get("depth", 0)
        is_new_branch = tutoring_state.get("is_new_branch", False)

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
            await _update_tutoring_state(
                session_id=session_id,
                current_node_id=new_node_id,
                question_id=question_id,
                depth=new_depth,
                request_id=request_id,
                is_new_branch=False,
            )

            is_complete = new_depth >= Config.TUTORING.MAX_INTERACTION_DEPTH
            next_prompt = None if is_complete else "Do you understand? Would you like me to explain further?"

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
    conversation_path = []
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
        await _update_tutoring_state(
            session_id=session_id,
            current_node_id=new_node_id,
            question_id=question_id,
            depth=depth + 1,
            request_id=request_id,
            is_new_branch=True,
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
