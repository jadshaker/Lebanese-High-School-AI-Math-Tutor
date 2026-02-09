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
        logger.info("  → Cache Search", request_id=request_id)

        result = await call_service(
            f"{Config.SERVICES.CACHE_URL}/search",
            {"embedding": embedding, "top_k": Config.CACHE_TOP_K},
            request_id,
            timeout=10,
        )

        results = result.get("results", [])
        duration = time.time() - start_time
        gateway_cache_search_duration_seconds.observe(duration)

        top_sim = results[0].get("similarity_score", 0) if results else 0
        logger.info(
            f"  ✓ Cache Search ({duration:.2f}s): {len(results)} results, top similarity: {top_sim:.2f}",
            request_id=request_id,
        )
        return results

    except (HTTPError, URLError) as e:
        duration = time.time() - start_time
        gateway_cache_search_duration_seconds.observe(duration)

        # Cache failure is non-critical, return empty results
        logger.warning(
            f"Cache search failed ({duration:.2f}s): {str(e)} (non-critical)",
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
                    similarity = cached["similarity_score"]
                    logger.info(
                        f"  ✓ Exact cache match found ({duration:.2f}s): similarity {similarity:.3f}",
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

        cached_info = (
            f"with {len(cached_results)} cached examples"
            if cached_results
            else "no cache context"
        )
        logger.info(f"  → Small LLM ({cached_info})", request_id=request_id)

        # Call Small LLM with OpenAI format
        result = await call_service(
            f"{Config.SERVICES.SMALL_LLM_URL}/v1/chat/completions",
            {
                "model": Config.MODELS.SMALL_LLM_MODEL_NAME,
                "messages": messages,
            },
            request_id,
            timeout=300,
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
            f"  ✓ Small LLM ({duration:.1f}s): {len(answer)} chars, confidence {confidence:.1f}",
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
            f"Small LLM service failed ({duration:.1f}s): {str(e)}",
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
        logger.info("  → Large LLM [cache miss]", request_id=request_id)

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
                "model": Config.MODELS.LARGE_LLM_MODEL_NAME,
                "messages": messages,
            },
            request_id,
            timeout=300,
        )

        answer = result["choices"][0]["message"]["content"]
        duration = time.time() - start_time
        gateway_large_llm_duration_seconds.observe(duration)

        # Record large LLM call
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
        logger.info("  → Cache Save", request_id=request_id)

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
            f"  ✓ Cache Save ({duration:.2f}s)",
            request_id=request_id,
        )

    except (HTTPError, URLError) as e:
        duration = time.time() - start_time
        gateway_cache_save_duration_seconds.observe(duration)

        # Cache save failure is non-critical, silently continue
        logger.warning(
            f"Cache save failed ({duration:.2f}s): {str(e)} (non-critical)",
            request_id=request_id,
        )


async def retrieve_answer(query: str, request_id: str) -> dict:
    """
    Execute Answer Retrieval pipeline

    Flow:
        1. Embed query (Embedding Service)
        2. Search cache (Cache Service)
        3. Query Small LLM with cache context
        4. If no exact match: Query Large LLM
        5. Save to cache

    Args:
        query: Reformulated query from Data Processing pipeline
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
    pipeline_start = time.time()
    latency: dict[str, float] = {}
    logger.info("Answer Retrieval Pipeline: Started", request_id=request_id)

    # Step 1: Embed the query
    t0 = time.time()
    embedding = await _embed_query(query, request_id)
    latency["embedding"] = round(time.time() - t0, 3)

    # Step 2: Search cache for similar Q&A pairs
    t0 = time.time()
    cached_results = await _search_cache(embedding, request_id)
    latency["cache_search"] = round(time.time() - t0, 3)

    # Step 3: Try Small LLM with cached results (or use exact match if found)
    t0 = time.time()
    small_llm_response = await _query_small_llm(query, cached_results, request_id)
    latency["small_llm"] = round(time.time() - t0, 3)

    # Step 4: Decision point - check if exact match
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

        latency["answer_retrieval_total"] = round(time.time() - pipeline_start, 3)
        logger.info(
            f"Answer Retrieval Pipeline: Completed - Exact cache match ({len(answer)} chars)",
            request_id=request_id,
        )

        return {
            "answer": answer,
            "source": "cache",
            "confidence": confidence,
            "used_cache": True,
            "latency": latency,
        }

    # Step 5: No exact match - call Large LLM
    # Record cache miss and large LLM call
    gateway_cache_misses_total.inc()

    t0 = time.time()
    large_llm_answer = await _query_large_llm(query, request_id)
    latency["large_llm"] = round(time.time() - t0, 3)

    # Step 6: Save Large LLM answer to cache
    t0 = time.time()
    await _save_to_cache(query, large_llm_answer, embedding, request_id)
    latency["cache_save"] = round(time.time() - t0, 3)

    latency["answer_retrieval_total"] = round(time.time() - pipeline_start, 3)
    logger.info(
        f"Answer Retrieval Pipeline: Completed - Large LLM used ({len(large_llm_answer)} chars)",
        request_id=request_id,
    )

    return {
        "answer": large_llm_answer,
        "source": "large_llm",
        "confidence": None,
        "used_cache": False,
        "latency": latency,
    }
