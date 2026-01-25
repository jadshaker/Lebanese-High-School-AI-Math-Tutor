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

logger = StructuredLogger("gateway")


async def _embed_query(query: str, request_id: str) -> list[float]:
    """
    Call Embedding Service to convert query to vector

    Args:
        query: User's question text
        request_id: Request ID for distributed tracing

    Returns:
        Embedding vector as list of floats

    Raises:
        HTTPException: If embedding service fails
    """
    start_time = time.time()
    try:
        logger.info(
            "Phase 2.1: Calling Embedding service",
            context={"query_length": len(query)},
            request_id=request_id,
        )

        result = await call_service(
            f"{Config.SERVICES.EMBEDDING_URL}/embed",
            {"text": query},
            request_id,
            timeout=10,
        )

        duration = time.time() - start_time
        gateway_embedding_duration_seconds.observe(duration)

        logger.info(
            "Embedding service responded",
            context={
                "embedding_dimension": len(result["embedding"]),
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        return result["embedding"]

    except Exception as e:
        duration = time.time() - start_time
        gateway_embedding_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="embedding_error").inc()

        logger.error(
            "Embedding service failed",
            context={
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        raise


async def _search_cache(embedding: list[float], request_id: str) -> list[dict]:
    """
    Search cache for similar Q&A pairs

    Args:
        embedding: Query embedding vector
        request_id: Request ID for distributed tracing

    Returns:
        List of similar cached Q&A pairs

    Raises:
        HTTPException: If cache service fails (non-critical)
    """
    start_time = time.time()
    try:
        logger.info(
            "Phase 2.2: Calling Cache service",
            context={"top_k": Config.CACHE_TOP_K},
            request_id=request_id,
        )

        result = await call_service(
            f"{Config.SERVICES.CACHE_URL}/search",
            {"embedding": embedding, "top_k": Config.CACHE_TOP_K},
            request_id,
            timeout=10,
        )

        results = result.get("results", [])
        duration = time.time() - start_time
        gateway_cache_search_duration_seconds.observe(duration)

        logger.info(
            "Cache service responded",
            context={
                "results_count": len(results),
                "top_similarity": (
                    results[0].get("similarity_score", 0) if results else 0
                ),
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        return results

    except (HTTPError, URLError) as e:
        duration = time.time() - start_time
        gateway_cache_search_duration_seconds.observe(duration)

        # Cache failure is non-critical, return empty results
        logger.warning(
            "Cache service failed (non-critical)",
            context={
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        return []


async def _query_small_llm(
    query: str, cached_results: list[dict], request_id: str
) -> dict:
    """
    Query Small LLM with cached context using OpenAI chat completions format

    Args:
        query: User's question
        cached_results: Similar cached Q&A pairs
        request_id: Request ID for distributed tracing

    Returns:
        Dict with answer, confidence, and is_exact_match

    Raises:
        HTTPException: If small LLM service fails
    """
    start_time = time.time()
    try:
        # Check for exact match in cached results (similarity >= 0.95)
        if cached_results:
            for cached in cached_results:
                if cached.get("similarity_score", 0) >= 0.95:
                    # Found exact match, return cached answer
                    duration = time.time() - start_time
                    logger.info(
                        "Phase 2.3: Exact match found in cache (skipping Small LLM)",
                        context={
                            "similarity_score": cached["similarity_score"],
                            "cached_question": cached.get("question", "")[:100],
                            "duration_seconds": round(duration, 3),
                        },
                        request_id=request_id,
                    )
                    return {
                        "answer": cached["answer"],
                        "confidence": cached["similarity_score"],
                        "is_exact_match": True,
                    }

        # No exact match - build OpenAI messages format
        messages = []

        # Add system message with cached context if available
        if cached_results and len(cached_results) > 0:
            context = "You are a math tutor. Here are some similar questions and answers for context:\n\n"
            for i, cached in enumerate(cached_results[:3], 1):
                context += f"{i}. Q: {cached['question']}\n   A: {cached['answer']}\n\n"
            context += "Use these examples to help answer the user's question."
            messages.append({"role": "system", "content": context})
        else:
            messages.append({"role": "system", "content": "You are a math tutor."})

        # Add user message
        messages.append({"role": "user", "content": query})

        logger.info(
            "Phase 2.3: Calling Small LLM service",
            context={
                "has_cached_context": len(cached_results) > 0,
                "cached_count": len(cached_results),
                "query": query[:100],
            },
            request_id=request_id,
        )

        # Call Small LLM with OpenAI format
        result = await call_service(
            f"{Config.SERVICES.SMALL_LLM_URL}/v1/chat/completions",
            {
                "model": "deepseek-r1:7b",
                "messages": messages,
            },
            request_id,
            timeout=60,
        )

        answer = result["choices"][0]["message"]["content"]
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)

        # Determine confidence based on whether we had cached context
        confidence = 0.7 if cached_results else 0.5

        # Record small LLM call
        gateway_llm_calls_total.labels(llm_service="small_llm").inc()

        # Record confidence
        gateway_confidence.observe(confidence)

        logger.info(
            "Small LLM service responded",
            context={
                "answer_length": len(answer),
                "answer_preview": answer[:100],
                "confidence": confidence,
                "is_exact_match": False,
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )

        return {
            "answer": answer,
            "confidence": confidence,
            "is_exact_match": False,
        }

    except Exception as e:
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="small_llm_error").inc()

        logger.error(
            "Small LLM service failed",
            context={
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        raise


async def _query_large_llm(query: str, request_id: str) -> str:
    """
    Query Large LLM for final answer using OpenAI chat completions format

    Args:
        query: User's question
        request_id: Request ID for distributed tracing

    Returns:
        Answer string from Large LLM

    Raises:
        HTTPException: If large LLM service fails
    """
    start_time = time.time()
    try:
        logger.info(
            "Phase 2.4: Calling Large LLM service (no exact match from cache/small LLM)",
            context={"query_length": len(query), "query": query[:100]},
            request_id=request_id,
        )

        # Build OpenAI messages format
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
                "model": "gpt-4o-mini",
                "messages": messages,
            },
            request_id,
            timeout=60,
        )

        answer = result["choices"][0]["message"]["content"]
        duration = time.time() - start_time
        gateway_large_llm_duration_seconds.observe(duration)

        # Record large LLM call
        gateway_llm_calls_total.labels(llm_service="large_llm").inc()

        logger.info(
            "Large LLM service responded",
            context={
                "answer_length": len(answer),
                "answer_preview": answer[:100],
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        return answer

    except Exception as e:
        duration = time.time() - start_time
        gateway_large_llm_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="large_llm_error").inc()

        logger.error(
            "Large LLM service failed",
            context={
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        raise


async def _save_to_cache(
    query: str, answer: str, embedding: list[float], request_id: str
) -> None:
    """
    Save Q&A pair to cache (non-critical operation)

    Args:
        query: User's question
        answer: Final answer
        embedding: Query embedding vector
        request_id: Request ID for distributed tracing
    """
    start_time = time.time()
    try:
        logger.info(
            "Phase 2.5: Saving to Cache service",
            context={"query_length": len(query), "answer_length": len(answer)},
            request_id=request_id,
        )

        await call_service(
            f"{Config.SERVICES.CACHE_URL}/save",
            {"question": query, "answer": answer, "embedding": embedding},
            request_id,
            timeout=10,
        )

        duration = time.time() - start_time
        gateway_cache_save_duration_seconds.observe(duration)

        # Successfully saved (or acknowledged in stub mode)
        logger.info(
            "Cache service save successful",
            context={"duration_seconds": round(duration, 3)},
            request_id=request_id,
        )

    except (HTTPError, URLError) as e:
        duration = time.time() - start_time
        gateway_cache_save_duration_seconds.observe(duration)

        # Cache save failure is non-critical, silently continue
        logger.warning(
            "Cache service save failed (non-critical)",
            context={
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )


async def run_phase2(query: str, request_id: str) -> dict:
    """
    Execute Phase 2: Answer Retrieval pipeline

    Flow:
        1. Embed query (Embedding Service)
        2. Search cache (Cache Service)
        3. Query Small LLM with cache context
        4. If no exact match: Query Large LLM
        5. Save to cache

    Args:
        query: Reformulated query from Phase 1
        request_id: Request ID for tracing

    Returns:
        Dict with:
            - answer: Final answer text
            - source: Source of answer ('cache', 'small_llm', 'large_llm')
            - confidence: Confidence score (if applicable)
            - used_cache: Whether cache was used

    Raises:
        HTTPException: If critical services fail
    """
    logger.info(
        "PHASE 2: Answer Retrieval - Starting",
        context={"query": query[:100]},
        request_id=request_id,
    )

    # Step 2.1: Embed the query
    embedding = await _embed_query(query, request_id)

    # Step 2.2: Search cache for similar Q&A pairs
    cached_results = await _search_cache(embedding, request_id)

    # Step 2.3: Try Small LLM with cached results (or use exact match if found)
    small_llm_response = await _query_small_llm(query, cached_results, request_id)

    # Step 2.4: Decision point - check if exact match
    if (
        small_llm_response.get("is_exact_match")
        and small_llm_response.get("answer") is not None
    ):
        # Exact match found, return Small LLM answer (cached answer)
        # Record cache hit
        gateway_cache_hits_total.inc()

        # Record confidence if available
        confidence = small_llm_response.get("confidence")
        if confidence is not None:
            gateway_confidence.observe(confidence)

        answer = small_llm_response["answer"]

        logger.info(
            "PHASE 2: Answer Retrieval - Completed (exact match from cache)",
            context={
                "source": "cache",
                "used_cache": True,
                "confidence": confidence,
                "answer_length": len(answer),
                "answer_preview": answer[:100],
            },
            request_id=request_id,
        )

        return {
            "answer": answer,
            "source": "cache",
            "confidence": confidence,
            "used_cache": True,
        }

    # Step 2.5: No exact match - call Large LLM
    # Record cache miss and large LLM call
    gateway_cache_misses_total.inc()

    large_llm_answer = await _query_large_llm(query, request_id)

    # Step 2.6: Save Large LLM answer to cache
    await _save_to_cache(query, large_llm_answer, embedding, request_id)

    logger.info(
        "PHASE 2: Answer Retrieval - Completed (large LLM used)",
        context={
            "source": "large_llm",
            "used_cache": False,
            "answer_length": len(large_llm_answer),
            "answer_preview": large_llm_answer[:100],
        },
        request_id=request_id,
    )

    return {
        "answer": large_llm_answer,
        "source": "large_llm",
        "confidence": None,
        "used_cache": False,
    }
