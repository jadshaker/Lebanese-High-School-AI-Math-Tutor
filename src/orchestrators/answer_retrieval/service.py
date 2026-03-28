import asyncio
import re
import time
from typing import Any

from src.clients.embedding import embedding_client
from src.clients.llm import large_llm_client, small_llm_client
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
from src.orchestrators.answer_retrieval.prompts import (
    ANSWER_GENERATION_SYSTEM_PROMPT,
    QUESTION_IDENTITY_SYSTEM_PROMPT,
)
from src.services.vector_cache import service as vector_cache

logger = StructuredLogger("gateway")


_SOLUTION_SEPARATOR = "---SOLUTION---"


def _clean_llm_response(response: str) -> str:
    """Strip <think>...</think> blocks from DeepSeek-R1 style responses."""
    if "</think>" in response:
        response = response.split("</think>")[-1].strip()
    elif "<think>" in response:
        response = response.split("<think>")[0].strip()
    return response


def _split_answer_and_solution(raw: str) -> tuple[str, str]:
    """Split an LLM response into the tutoring answer and the hidden solution.

    Returns (answer_text, final_solution).  If the separator is missing the
    entire response is treated as the answer and the solution is empty.
    """
    if _SOLUTION_SEPARATOR in raw:
        parts = raw.split(_SOLUTION_SEPARATOR, 1)
        return parts[0].strip(), parts[1].strip()
    return raw.strip(), ""


async def _embed_query(query: str, request_id: str) -> list[float]:
    """Embed query using OpenAI embeddings API."""
    start_time = time.time()
    try:
        logger.info("  → Embedding Service", request_id=request_id)

        if not embedding_client:
            raise RuntimeError("Embedding client not configured")

        response = await asyncio.to_thread(
            embedding_client.embeddings.create,
            model=Config.EMBEDDING.MODEL,
            input=query,
            dimensions=Config.EMBEDDING.DIMENSIONS,
        )

        duration = time.time() - start_time
        gateway_embedding_duration_seconds.observe(duration)

        embedding = response.data[0].embedding
        logger.info(
            f"  ✓ Embedding Service ({duration:.1f}s): {len(embedding)}D vector",
            request_id=request_id,
        )
        return embedding

    except Exception as e:
        duration = time.time() - start_time
        gateway_embedding_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="embedding_error").inc()
        logger.error(
            f"Embedding failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def _search_cache(embedding: list[float], request_id: str) -> list[dict]:
    """Search vector cache for similar Q&A pairs."""
    start_time = time.time()
    try:
        logger.info("  → Vector Cache Search", request_id=request_id)

        results = await vector_cache.search_questions(
            embedding=embedding,
            top_k=Config.CACHE_TOP_K,
            request_id=request_id,
        )

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


async def _check_question_identity(
    query: str, cached_results: list[dict], request_id: str
) -> dict | None:
    """Ask the small LLM if the new question is identical to any cached question.

    Returns the matched cached result dict (with id, answer_text, etc.) or None.
    """
    if not cached_results:
        return None

    start_time = time.time()
    try:
        candidates = ""
        for i, cached in enumerate(cached_results[:5], 1):
            candidates += f"{i}. {cached.get('question_text', '')}\n"

        messages = [
            {"role": "system", "content": QUESTION_IDENTITY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"New question: {query}\n\nCached questions:\n{candidates}",
            },
        ]

        logger.info("  → Small LLM (question identity check)", request_id=request_id)

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
        gateway_llm_calls_total.labels(llm_service="small_llm_identity_check").inc()

        logger.info(
            f"  ✓ Small LLM identity check ({duration:.1f}s): {response_text}",
            request_id=request_id,
        )

        match = re.search(r"\bMATCH\s+(\d+)\b", response_text, re.IGNORECASE)
        if match:
            try:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(cached_results):
                    matched = cached_results[idx]
                    logger.info(
                        f"Question identity match: cached question #{idx + 1}",
                        context={"question_id": matched.get("id", "")},
                        request_id=request_id,
                    )
                    return matched
            except (ValueError, IndexError):
                pass

        logger.info("No question identity match found", request_id=request_id)
        return None

    except Exception as e:
        duration = time.time() - start_time
        gateway_small_llm_duration_seconds.observe(duration)
        logger.warning(
            f"Question identity check failed ({duration:.1f}s): {str(e)} — treating as no match",
            request_id=request_id,
        )
        return None


async def _generate_answer(query: str, request_id: str) -> tuple[str, str]:
    """Generate a new answer using the Large LLM.

    Returns (answer_text, final_solution).
    """
    start_time = time.time()
    try:
        logger.info("  → Large LLM (answer generation)", request_id=request_id)

        if not large_llm_client:
            raise RuntimeError("Large LLM client not configured")

        messages = [
            {"role": "system", "content": ANSWER_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        call_params: dict[str, Any] = {
            "model": Config.LARGE_LLM.MODEL_NAME,
            "messages": messages,
            "temperature": Config.LARGE_LLM.TEMPERATURE,
            "top_p": Config.LARGE_LLM.TOP_P,
        }
        if Config.LARGE_LLM.MAX_TOKENS is not None:
            call_params["max_tokens"] = Config.LARGE_LLM.MAX_TOKENS

        result = await asyncio.to_thread(
            large_llm_client.chat.completions.create, **call_params  # type: ignore[arg-type]
        )

        raw = _clean_llm_response(result.choices[0].message.content or "")
        answer, final_solution = _split_answer_and_solution(raw)
        duration = time.time() - start_time
        gateway_large_llm_duration_seconds.observe(duration)
        gateway_llm_calls_total.labels(llm_service="large_llm").inc()

        logger.info(
            f"  ✓ Large LLM ({duration:.1f}s): {len(answer)} chars answer, {len(final_solution)} chars solution",
            request_id=request_id,
        )
        return answer, final_solution

    except Exception as e:
        duration = time.time() - start_time
        gateway_large_llm_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="large_llm_error").inc()
        logger.error(
            f"Large LLM failed ({duration:.1f}s): {str(e)}",
            request_id=request_id,
        )
        raise


async def _save_to_cache(
    original_query: str,
    reformulated_query: str,
    answer: str,
    final_solution: str,
    embedding: list[float],
    request_id: str,
) -> str:
    """Save Q&A pair to vector cache (non-critical). Returns question_id."""
    start_time = time.time()
    try:
        logger.info("  → Vector Cache Save", request_id=request_id)

        question_id = await vector_cache.add_question(
            question_text=original_query,
            reformulated_text=reformulated_query,
            answer_text=answer,
            final_solution=final_solution,
            embedding=embedding,
            request_id=request_id,
        )

        duration = time.time() - start_time
        gateway_cache_save_duration_seconds.observe(duration)
        logger.info(f"  ✓ Vector Cache Save ({duration:.2f}s)", request_id=request_id)
        return question_id

    except Exception as e:
        duration = time.time() - start_time
        gateway_cache_save_duration_seconds.observe(duration)
        logger.warning(
            f"Cache save failed ({duration:.2f}s): {str(e)} (non-critical)",
            request_id=request_id,
        )
        return ""


async def retrieve_answer(
    query: str, request_id: str, original_query: str = ""
) -> dict:
    """
    Answer retrieval pipeline.

    Flow:
        1. Embed the reformulated query
        2. Search vector cache for top-K similar questions
        3. Small LLM identity check: is this the same as a cached question?
        4. If match → return cached answer + question_id
        5. If no match → Large LLM generates new answer → save to cache

    Returns dict with: answer, source, question_id, reused_question,
                       confidence, latency
    """
    original_query = original_query or query
    pipeline_start = time.time()
    latency: dict[str, float] = {}
    logger.info("Answer Retrieval Pipeline: Started", request_id=request_id)

    # Step 1: Embed the query
    t0 = time.time()
    embedding = await _embed_query(query, request_id)
    latency["embedding"] = round(time.time() - t0, 3)

    # Step 2: Search vector cache
    t0 = time.time()
    cached_results = await _search_cache(embedding, request_id)
    latency["cache_search"] = round(time.time() - t0, 3)

    top_confidence = cached_results[0].get("score", 0) if cached_results else 0
    gateway_confidence.observe(top_confidence)

    # Step 3: Small LLM identity check on candidates
    matched = None
    if cached_results:
        t0 = time.time()
        matched = await _check_question_identity(query, cached_results, request_id)
        latency["identity_check"] = round(time.time() - t0, 3)

    # Step 4: Cache hit — return cached answer
    if matched:
        gateway_cache_hits_total.inc()
        question_id = matched.get("id", "")
        answer = matched.get("answer_text", "")
        final_solution = matched.get("final_solution", "")

        logger.info(
            f"Answer Retrieval Pipeline: Cache HIT (question_id={question_id})",
            request_id=request_id,
        )

        latency["answer_retrieval_total"] = round(time.time() - pipeline_start, 3)

        return {
            "answer": answer,
            "final_solution": final_solution,
            "source": "cache_hit",
            "question_id": question_id,
            "reused_question": True,
            "confidence": top_confidence,
            "latency": latency,
        }

    # Step 5: Cache miss — generate with Large LLM
    gateway_cache_misses_total.inc()

    t0 = time.time()
    answer, final_solution = await _generate_answer(query, request_id)
    latency["llm"] = round(time.time() - t0, 3)

    # Save to cache
    t0 = time.time()
    question_id = await _save_to_cache(
        original_query, query, answer, final_solution, embedding, request_id
    )
    latency["cache_save"] = round(time.time() - t0, 3)

    latency["answer_retrieval_total"] = round(time.time() - pipeline_start, 3)

    logger.info(
        f"Answer Retrieval Pipeline: Completed - generated ({len(answer)} chars)",
        request_id=request_id,
    )

    return {
        "answer": answer,
        "final_solution": final_solution,
        "source": "generated",
        "question_id": question_id,
        "reused_question": False,
        "confidence": top_confidence,
        "latency": latency,
    }
