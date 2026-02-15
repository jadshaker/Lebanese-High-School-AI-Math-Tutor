import re
import time

from src.clients.http_client import call_service
from src.config import Config
from src.logging_utils import StructuredLogger
from src.metrics import (
    gateway_cache_hits_total,
    gateway_cache_misses_total,
    gateway_cache_save_duration_seconds,
    gateway_cache_search_duration_seconds,
    gateway_confidence,
    gateway_embedding_duration_seconds,
    gateway_errors_total,
    gateway_large_llm_duration_seconds,
    gateway_llm_calls_total,
    gateway_small_llm_duration_seconds,
)
from src.models.schemas import ConfidenceTier

logger = StructuredLogger("gateway")


def _determine_tier(confidence: float) -> ConfidenceTier:
    """Determine which tier to use based on confidence score."""
    thresholds = Config.CONFIDENCE_TIERS
    if confidence >= thresholds.TIER_1_THRESHOLD:
        return ConfidenceTier.TIER_1_SMALL_LLM_VALIDATE_OR_GENERATE
    elif confidence >= thresholds.TIER_2_THRESHOLD:
        return ConfidenceTier.TIER_2_SMALL_LLM_CONTEXT
    elif confidence >= thresholds.TIER_3_THRESHOLD:
        return ConfidenceTier.TIER_3_FINE_TUNED
    else:
        return ConfidenceTier.TIER_4_LARGE_LLM


async def _embed_query(query: str, request_id: str) -> list[float]:
    """Call Embedding Service to convert query to vector."""
    start_time = time.time()
    try:
        logger.info("  → Embedding Service", request_id=request_id)

        result = await call_service(
            f"{Config.SERVICES.EMBEDDING_URL}/embed",
            {"text": query},
            request_id,
            timeout=10,
        )

        duration = time.time() - start_time
        gateway_embedding_duration_seconds.observe(duration)

        dim = len(result["embedding"])
        logger.info(
            f"  ✓ Embedding Service ({duration:.1f}s): {dim}D vector",
            request_id=request_id,
        )
        return result["embedding"]

    except Exception as e:
        duration = time.time() - start_time
        gateway_embedding_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="embedding_error").inc()

        logger.error(
            f"Embedding service failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def _search_cache(embedding: list[float], request_id: str) -> list[dict]:
    """Search vector cache for similar Q&A pairs."""
    start_time = time.time()
    try:
        logger.info("  → Vector Cache Search", request_id=request_id)

        result = await call_service(
            f"{Config.SERVICES.VECTOR_CACHE_URL}/search",
            {"embedding": embedding, "top_k": Config.CACHE_TOP_K},
            request_id,
            timeout=10,
        )

        results = result.get("results", [])
        duration = time.time() - start_time
        gateway_cache_search_duration_seconds.observe(duration)

        top_sim = results[0].get("score", 0) if results else 0
        logger.info(
            f"  ✓ Vector Cache Search ({duration:.2f}s): {len(results)} results, top similarity: {top_sim:.2f}",
            request_id=request_id,
        )
        return results

    except Exception as e:
        duration = time.time() - start_time
        gateway_cache_search_duration_seconds.observe(duration)

        logger.warning(
            f"Cache search failed ({duration:.2f}s): {str(e)} (non-critical)",
            request_id=request_id,
        )
        return []


def _clean_llm_response(response: str) -> str:
    """Strip <think>...</think> blocks from DeepSeek-R1 style responses."""
    if "<think>" in response:
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
    return response


async def _validate_or_generate_with_small_llm(
    query: str, cached_question: str, cached_answer: str, request_id: str
) -> dict:
    """
    Tier 1: Use Small LLM to validate cached answer OR generate a new one.

    Single LLM call that checks if the cached answer is valid for the query,
    and if not, generates a correct answer using the cached Q&A as context.

    Returns:
        dict with "answer" (str) and "cache_reused" (bool)
    """
    start_time = time.time()
    try:
        messages = [
            {
                "role": "system",
                "content": """You are a math answer validator and generator.
You will receive a user's question and a cached question-answer pair.

If the cached answer correctly and completely answers the user's question, respond with:
CACHE_VALID
<the cached answer, unchanged>

If the cached answer does NOT correctly answer the user's question, respond with:
GENERATED
<your own correct answer to the user's question>

You MUST start your response with either CACHE_VALID or GENERATED on the first line, followed by the answer on subsequent lines.""",
            },
            {
                "role": "user",
                "content": f"User's Question: {query}\n\nCached Question: {cached_question}\n\nCached Answer: {cached_answer}",
            },
        ]

        logger.info("  → Small LLM (validate-or-generate)", request_id=request_id)

        result = await call_service(
            f"{Config.SERVICES.SMALL_LLM_URL}/v1/chat/completions",
            {
                "model": Config.MODELS.SMALL_LLM_MODEL_NAME,
                "messages": messages,
                "temperature": Config.MODELS.TEMPERATURE,
                "top_p": Config.MODELS.TOP_P,
            },
            request_id,
            timeout=Config.MODELS.TIMEOUT,
        )

        response_text = result["choices"][0]["message"]["content"]
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)
        gateway_llm_calls_total.labels(
            llm_service="small_llm_validate_or_generate"
        ).inc()

        # Clean <think> blocks from DeepSeek-R1
        response_text = _clean_llm_response(response_text)

        # Parse the prefix
        lines = response_text.strip().split("\n", 1)
        prefix = lines[0].strip().upper()
        answer_text = lines[1].strip() if len(lines) > 1 else ""

        if prefix == "CACHE_VALID":
            # Use the cached answer (LLM confirmed it's valid)
            answer = answer_text if answer_text else cached_answer
            cache_reused = True
            logger.info(
                f"  ✓ Small LLM validate-or-generate ({duration:.1f}s): CACHE_VALID ({len(answer)} chars)",
                request_id=request_id,
            )
        else:
            # LLM generated a new answer (GENERATED prefix or unrecognized)
            answer = answer_text if answer_text else response_text
            cache_reused = False
            logger.info(
                f"  ✓ Small LLM validate-or-generate ({duration:.1f}s): GENERATED ({len(answer)} chars)",
                request_id=request_id,
            )

        return {"answer": answer, "cache_reused": cache_reused}

    except Exception as e:
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)
        gateway_errors_total.labels(
            error_type="small_llm_validate_or_generate_error"
        ).inc()

        logger.error(
            f"Small LLM validate-or-generate failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def _query_small_llm_with_context(
    query: str, cached_results: list[dict], request_id: str
) -> str:
    """
    Tier 2: Query Small LLM with cached context to generate answer.
    """
    start_time = time.time()
    try:
        context = "You are a math tutor. Here are some similar questions and answers for context:\n\n"
        for i, cached in enumerate(cached_results[:3], 1):
            context += (
                f"{i}. Q: {cached['question_text']}\n   A: {cached['answer_text']}\n\n"
            )
        context += "Use these examples to help answer the user's question accurately."

        messages = [
            {"role": "system", "content": context},
            {"role": "user", "content": query},
        ]

        logger.info(
            f"  → Small LLM (with {len(cached_results)} context examples)",
            request_id=request_id,
        )

        result = await call_service(
            f"{Config.SERVICES.SMALL_LLM_URL}/v1/chat/completions",
            {
                "model": Config.MODELS.SMALL_LLM_MODEL_NAME,
                "messages": messages,
                "temperature": Config.MODELS.TEMPERATURE,
                "top_p": Config.MODELS.TOP_P,
            },
            request_id,
            timeout=Config.MODELS.TIMEOUT,
        )

        answer = result["choices"][0]["message"]["content"]
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)
        gateway_llm_calls_total.labels(llm_service="small_llm_context").inc()

        logger.info(
            f"  ✓ Small LLM with context ({duration:.1f}s): {len(answer)} chars",
            request_id=request_id,
        )
        return answer

    except Exception as e:
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="small_llm_context_error").inc()

        logger.error(
            f"Small LLM with context failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def _query_fine_tuned_model(query: str, request_id: str) -> str:
    """
    Tier 3: Query fine-tuned model for domain-specific answer.
    """
    start_time = time.time()
    try:
        messages = [
            {
                "role": "system",
                "content": "You are an expert mathematics tutor for Lebanese high school students.",
            },
            {"role": "user", "content": query},
        ]

        logger.info("  → Fine-Tuned Model", request_id=request_id)

        result = await call_service(
            f"{Config.SERVICES.FINE_TUNED_MODEL_URL}/v1/chat/completions",
            {
                "model": Config.MODELS.FINE_TUNED_MODEL_NAME,
                "messages": messages,
                "temperature": Config.MODELS.TEMPERATURE,
                "top_p": Config.MODELS.TOP_P,
            },
            request_id,
            timeout=Config.MODELS.TIMEOUT,
        )

        answer = result["choices"][0]["message"]["content"]
        duration = time.time() - start_time
        gateway_llm_calls_total.labels(llm_service="fine_tuned").inc()

        logger.info(
            f"  ✓ Fine-Tuned Model ({duration:.1f}s): {len(answer)} chars",
            request_id=request_id,
        )
        return answer

    except Exception as e:
        duration = time.time() - start_time
        gateway_errors_total.labels(error_type="fine_tuned_error").inc()

        logger.error(
            f"Fine-tuned model failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def _query_large_llm(query: str, request_id: str) -> str:
    """
    Tier 4: Query Large LLM for complex or novel questions.
    """
    start_time = time.time()
    try:
        logger.info("  → Large LLM", request_id=request_id)

        messages = [
            {
                "role": "system",
                "content": "You are an expert mathematics tutor for Lebanese high school students. Provide clear, accurate, and educational answers to math questions.",
            },
            {"role": "user", "content": query},
        ]

        result = await call_service(
            f"{Config.SERVICES.LARGE_LLM_URL}/v1/chat/completions",
            {
                "model": Config.MODELS.LARGE_LLM_MODEL_NAME,
                "messages": messages,
                "temperature": Config.MODELS.TEMPERATURE,
                "top_p": Config.MODELS.TOP_P,
            },
            request_id,
            timeout=Config.MODELS.TIMEOUT,
        )

        answer = result["choices"][0]["message"]["content"]
        duration = time.time() - start_time
        gateway_large_llm_duration_seconds.observe(duration)
        gateway_llm_calls_total.labels(llm_service="large_llm").inc()

        logger.info(
            f"  ✓ Large LLM ({duration:.1f}s): {len(answer)} chars",
            request_id=request_id,
        )
        return answer

    except Exception as e:
        duration = time.time() - start_time
        gateway_large_llm_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="large_llm_error").inc()

        logger.error(
            f"Large LLM service failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def _save_to_cache(
    original_query: str,
    reformulated_query: str,
    answer: str,
    embedding: list[float],
    request_id: str,
) -> None:
    """Save Q&A pair to vector cache (non-critical operation)."""
    start_time = time.time()
    try:
        logger.info("  → Vector Cache Save", request_id=request_id)

        await call_service(
            f"{Config.SERVICES.VECTOR_CACHE_URL}/questions",
            {
                "question_text": original_query,
                "reformulated_text": reformulated_query,
                "answer_text": answer,
                "embedding": embedding,
            },
            request_id,
            timeout=10,
        )

        duration = time.time() - start_time
        gateway_cache_save_duration_seconds.observe(duration)

        logger.info(f"  ✓ Vector Cache Save ({duration:.2f}s)", request_id=request_id)

    except Exception as e:
        duration = time.time() - start_time
        gateway_cache_save_duration_seconds.observe(duration)

        logger.warning(
            f"Cache save failed ({duration:.2f}s): {str(e)} (non-critical)",
            request_id=request_id,
        )


async def retrieve_answer(
    query: str, request_id: str, original_query: str = ""
) -> dict:
    """
    Execute 4-Tier Answer Retrieval pipeline.

    Tiers:
        1. Small LLM validate-or-generate (>=0.85): Validate cached answer or generate new
        2. Small LLM with context (0.70-0.85): Generate with cached examples
        3. Fine-tuned model (0.50-0.70): Use domain-specific model
        4. Large LLM (<0.50): Use powerful model for novel questions

    Args:
        query: Reformulated query from Data Processing pipeline
        request_id: Request ID for tracing
        original_query: Original user query before reformulation

    Returns:
        Dict with:
            - answer: Final answer text
            - source: Source tier description
            - tier: ConfidenceTier enum value
            - confidence: Confidence score
            - used_cache: Whether cache was used
            - cache_reused: Whether cached answer was reused (Tier 1 only)
    """
    original_query = original_query or query
    logger.info("4-Tier Answer Retrieval Pipeline: Started", request_id=request_id)

    # Step 1: Embed the query
    embedding = await _embed_query(query, request_id)

    # Step 2: Search vector cache
    cached_results = await _search_cache(embedding, request_id)

    # Determine confidence and tier
    top_confidence = cached_results[0].get("score", 0) if cached_results else 0
    tier = _determine_tier(top_confidence)
    gateway_confidence.observe(top_confidence)

    logger.info(
        f"Routing decision: confidence={top_confidence:.3f}, tier={tier.value}",
        request_id=request_id,
    )

    answer = None
    source = tier.value
    used_cache = False
    cache_reused = None

    # Execute based on tier
    if tier == ConfidenceTier.TIER_1_SMALL_LLM_VALIDATE_OR_GENERATE:
        # Tier 1: Small LLM validates cached answer or generates new one
        cached_question = cached_results[0]["question_text"]
        cached_answer = cached_results[0]["answer_text"]

        try:
            result = await _validate_or_generate_with_small_llm(
                query, cached_question, cached_answer, request_id
            )
            answer = result["answer"]
            cache_reused = result["cache_reused"]

            if cache_reused:
                gateway_cache_hits_total.inc()
                used_cache = True
                source = f"{tier.value}_cache_reused"
                logger.info(
                    f"Tier 1: Cache validated ({len(answer)} chars)",
                    request_id=request_id,
                )
            else:
                gateway_cache_misses_total.inc()
                source = f"{tier.value}_generated"
                logger.info(
                    f"Tier 1: Generated new answer ({len(answer)} chars)",
                    request_id=request_id,
                )
                await _save_to_cache(
                    original_query, query, answer, embedding, request_id
                )

        except Exception:
            # Fallback to Large LLM if Small LLM fails
            logger.warning(
                "Tier 1: Small LLM failed, falling back to Large LLM",
                request_id=request_id,
            )
            gateway_cache_misses_total.inc()
            answer = await _query_large_llm(query, request_id)
            source = f"{tier.value}_fallback"
            await _save_to_cache(original_query, query, answer, embedding, request_id)

    elif tier == ConfidenceTier.TIER_2_SMALL_LLM_CONTEXT:
        # Tier 2: Small LLM with cached context
        gateway_cache_misses_total.inc()
        answer = await _query_small_llm_with_context(query, cached_results, request_id)
        await _save_to_cache(original_query, query, answer, embedding, request_id)

    elif tier == ConfidenceTier.TIER_3_FINE_TUNED:
        # Tier 3: Fine-tuned model
        gateway_cache_misses_total.inc()
        try:
            answer = await _query_fine_tuned_model(query, request_id)
        except Exception:
            # Fallback to Large LLM if fine-tuned fails
            logger.warning(
                "Tier 3: Fine-tuned failed, falling back to Large LLM",
                request_id=request_id,
            )
            answer = await _query_large_llm(query, request_id)
            source = f"{tier.value}_fallback"
        await _save_to_cache(original_query, query, answer, embedding, request_id)

    else:
        # Tier 4: Large LLM
        gateway_cache_misses_total.inc()
        answer = await _query_large_llm(query, request_id)
        await _save_to_cache(original_query, query, answer, embedding, request_id)

    logger.info(
        f"4-Tier Answer Retrieval Pipeline: Completed - {source} ({len(answer)} chars)",
        request_id=request_id,
    )

    return {
        "answer": answer,
        "source": source,
        "tier": tier,
        "confidence": top_confidence,
        "used_cache": used_cache,
        "cache_reused": cache_reused,
    }
