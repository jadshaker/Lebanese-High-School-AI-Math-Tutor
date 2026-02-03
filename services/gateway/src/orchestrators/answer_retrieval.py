import time
from urllib.error import HTTPError, URLError

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
        return ConfidenceTier.TIER_1_DIRECT_CACHE
    elif confidence >= thresholds.TIER_2_THRESHOLD:
        return ConfidenceTier.TIER_2_SMALL_LLM_VALIDATE
    elif confidence >= thresholds.TIER_3_THRESHOLD:
        return ConfidenceTier.TIER_3_SMALL_LLM_CONTEXT
    elif confidence >= thresholds.TIER_4_THRESHOLD:
        return ConfidenceTier.TIER_4_FINE_TUNED
    else:
        return ConfidenceTier.TIER_5_LARGE_LLM


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

        top_sim = results[0].get("similarity_score", 0) if results else 0
        logger.info(
            f"  ✓ Vector Cache Search ({duration:.2f}s): {len(results)} results, top similarity: {top_sim:.2f}",
            request_id=request_id,
        )
        return results

    except (HTTPError, URLError) as e:
        duration = time.time() - start_time
        gateway_cache_search_duration_seconds.observe(duration)

        logger.warning(
            f"Cache search failed ({duration:.2f}s): {str(e)} (non-critical)",
            request_id=request_id,
        )
        return []


async def _validate_with_small_llm(
    query: str, cached_answer: str, request_id: str
) -> dict:
    """
    Tier 2: Use Small LLM to validate if cached answer is appropriate.
    Returns validation result with confidence.
    """
    start_time = time.time()
    try:
        messages = [
            {
                "role": "system",
                "content": """You are a math answer validator. Given a question and a cached answer,
determine if the cached answer correctly and completely addresses the question.
Reply with ONLY 'VALID' or 'INVALID' followed by a brief reason.""",
            },
            {
                "role": "user",
                "content": f"Question: {query}\n\nCached Answer: {cached_answer}\n\nIs this answer valid for this question?",
            },
        ]

        logger.info("  → Small LLM (validation)", request_id=request_id)

        result = await call_service(
            f"{Config.SERVICES.SMALL_LLM_URL}/v1/chat/completions",
            {"model": "deepseek-r1:7b", "messages": messages},
            request_id,
            timeout=30,
        )

        response_text = result["choices"][0]["message"]["content"]
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)
        gateway_llm_calls_total.labels(llm_service="small_llm_validate").inc()

        is_valid = response_text.strip().upper().startswith("VALID")

        logger.info(
            f"  ✓ Small LLM validation ({duration:.1f}s): {'VALID' if is_valid else 'INVALID'}",
            request_id=request_id,
        )

        return {"is_valid": is_valid, "reasoning": response_text}

    except Exception as e:
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="small_llm_validate_error").inc()

        logger.error(
            f"Small LLM validation failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        return {"is_valid": False, "reasoning": "Validation failed"}


async def _query_small_llm_with_context(
    query: str, cached_results: list[dict], request_id: str
) -> str:
    """
    Tier 3: Query Small LLM with cached context to generate answer.
    """
    start_time = time.time()
    try:
        context = "You are a math tutor. Here are some similar questions and answers for context:\n\n"
        for i, cached in enumerate(cached_results[:3], 1):
            context += f"{i}. Q: {cached['question']}\n   A: {cached['answer']}\n\n"
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
            {"model": "deepseek-r1:7b", "messages": messages},
            request_id,
            timeout=60,
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
    Tier 4: Query fine-tuned model for domain-specific answer.
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
            {"model": "tinyllama:latest", "messages": messages},
            request_id,
            timeout=60,
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
    Tier 5: Query Large LLM for complex or novel questions.
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
            {"model": "gpt-4o-mini", "messages": messages},
            request_id,
            timeout=60,
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
    query: str, answer: str, embedding: list[float], request_id: str
) -> None:
    """Save Q&A pair to vector cache (non-critical operation)."""
    start_time = time.time()
    try:
        logger.info("  → Vector Cache Save", request_id=request_id)

        await call_service(
            f"{Config.SERVICES.VECTOR_CACHE_URL}/questions",
            {"question": query, "answer": answer, "embedding": embedding},
            request_id,
            timeout=10,
        )

        duration = time.time() - start_time
        gateway_cache_save_duration_seconds.observe(duration)

        logger.info(f"  ✓ Vector Cache Save ({duration:.2f}s)", request_id=request_id)

    except (HTTPError, URLError) as e:
        duration = time.time() - start_time
        gateway_cache_save_duration_seconds.observe(duration)

        logger.warning(
            f"Cache save failed ({duration:.2f}s): {str(e)} (non-critical)",
            request_id=request_id,
        )


async def retrieve_answer(query: str, request_id: str) -> dict:
    """
    Execute 5-Tier Answer Retrieval pipeline.

    Tiers:
        1. Direct cache (≥0.95): Return cached answer immediately
        2. Small LLM validate (0.85-0.95): Validate cached answer before use
        3. Small LLM with context (0.70-0.85): Generate with cached examples
        4. Fine-tuned model (0.50-0.70): Use domain-specific model
        5. Large LLM (<0.50): Use powerful model for novel questions

    Args:
        query: Reformulated query from Data Processing pipeline
        request_id: Request ID for tracing

    Returns:
        Dict with:
            - answer: Final answer text
            - source: Source tier description
            - tier: ConfidenceTier enum value
            - confidence: Confidence score
            - used_cache: Whether cache was used
    """
    logger.info("5-Tier Answer Retrieval Pipeline: Started", request_id=request_id)

    # Step 1: Embed the query
    embedding = await _embed_query(query, request_id)

    # Step 2: Search vector cache
    cached_results = await _search_cache(embedding, request_id)

    # Determine confidence and tier
    top_confidence = cached_results[0].get("similarity_score", 0) if cached_results else 0
    tier = _determine_tier(top_confidence)
    gateway_confidence.observe(top_confidence)

    logger.info(
        f"Routing decision: confidence={top_confidence:.3f}, tier={tier.value}",
        request_id=request_id,
    )

    answer = None
    source = tier.value

    # Execute based on tier
    if tier == ConfidenceTier.TIER_1_DIRECT_CACHE:
        # Tier 1: Direct cache hit
        gateway_cache_hits_total.inc()
        answer = cached_results[0]["answer"]
        logger.info(
            f"Tier 1: Direct cache hit ({len(answer)} chars)", request_id=request_id
        )

    elif tier == ConfidenceTier.TIER_2_SMALL_LLM_VALIDATE:
        # Tier 2: Validate with Small LLM
        cached_answer = cached_results[0]["answer"]
        validation = await _validate_with_small_llm(query, cached_answer, request_id)

        if validation["is_valid"]:
            gateway_cache_hits_total.inc()
            answer = cached_answer
            logger.info(
                f"Tier 2: Validation passed, using cache ({len(answer)} chars)",
                request_id=request_id,
            )
        else:
            # Validation failed, escalate to Large LLM
            gateway_cache_misses_total.inc()
            logger.info(
                "Tier 2: Validation failed, escalating to Large LLM",
                request_id=request_id,
            )
            answer = await _query_large_llm(query, request_id)
            source = f"{tier.value}_escalated"
            await _save_to_cache(query, answer, embedding, request_id)

    elif tier == ConfidenceTier.TIER_3_SMALL_LLM_CONTEXT:
        # Tier 3: Small LLM with cached context
        gateway_cache_misses_total.inc()
        answer = await _query_small_llm_with_context(query, cached_results, request_id)
        await _save_to_cache(query, answer, embedding, request_id)

    elif tier == ConfidenceTier.TIER_4_FINE_TUNED:
        # Tier 4: Fine-tuned model
        gateway_cache_misses_total.inc()
        try:
            answer = await _query_fine_tuned_model(query, request_id)
        except Exception:
            # Fallback to Large LLM if fine-tuned fails
            logger.warning(
                "Tier 4: Fine-tuned failed, falling back to Large LLM",
                request_id=request_id,
            )
            answer = await _query_large_llm(query, request_id)
            source = f"{tier.value}_fallback"
        await _save_to_cache(query, answer, embedding, request_id)

    else:
        # Tier 5: Large LLM
        gateway_cache_misses_total.inc()
        answer = await _query_large_llm(query, request_id)
        await _save_to_cache(query, answer, embedding, request_id)

    logger.info(
        f"5-Tier Answer Retrieval Pipeline: Completed - {source} ({len(answer)} chars)",
        request_id=request_id,
    )

    return {
        "answer": answer,
        "source": source,
        "tier": tier,
        "confidence": top_confidence,
        "used_cache": tier in [
            ConfidenceTier.TIER_1_DIRECT_CACHE,
            ConfidenceTier.TIER_2_SMALL_LLM_VALIDATE,
        ],
    }
