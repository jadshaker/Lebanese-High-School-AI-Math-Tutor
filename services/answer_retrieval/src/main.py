import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from src.config import Config
from src.logging_utils import (
    StructuredLogger,
    generate_request_id,
    get_logs_by_request_id,
)
from src.metrics import (
    answer_retrieval_cache_hits_total,
    answer_retrieval_cache_misses_total,
    answer_retrieval_confidence,
    answer_retrieval_llm_calls_total,
    http_request_duration_seconds,
    http_requests_total,
)
from src.models.schemas import RetrieveAnswerRequest, RetrieveAnswerResponse

app = FastAPI(title="Answer Retrieval Service", version="1.0.0")
logger = StructuredLogger("answer_retrieval")


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Middleware to log all HTTP requests and responses, and record metrics"""
    # Get request_id from header or generate new one
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = generate_request_id()

    start_time = time.time()

    # Skip logging /metrics endpoint unless there's an error
    is_metrics_endpoint = request.url.path == "/metrics"

    # Log incoming request (skip /metrics)
    if not is_metrics_endpoint:
        logger.info(
            "Incoming request",
            context={
                "endpoint": request.url.path,
                "method": request.method,
                "client": request.client.host if request.client else "unknown",
            },
            request_id=request_id,
        )

    # Store request_id in request state for access in handlers
    request.state.request_id = request_id

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Record metrics (skip /metrics endpoint to avoid recursion)
        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="answer_retrieval",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="answer_retrieval",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

        # Log response (skip /metrics if status is 200)
        if not (is_metrics_endpoint and response.status_code == 200):
            logger.info(
                "Request completed",
                context={
                    "endpoint": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_seconds": round(duration, 3),
                },
                request_id=request_id,
            )

        # Add request_id to response headers
        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as e:
        duration = time.time() - start_time

        # Record error metrics
        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="answer_retrieval",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="answer_retrieval",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

        # Always log errors, even for /metrics
        logger.error(
            "Request failed",
            context={
                "endpoint": request.url.path,
                "method": request.method,
                "error": str(e),
                "duration_seconds": round(duration, 3),
            },
            request_id=request_id,
        )
        raise


@app.get("/health")
def health_check() -> dict[str, str | dict]:
    """
    Health check endpoint that verifies all dependent services

    Returns:
        Dict with overall status and individual service statuses
    """
    services_status = {}
    overall_healthy = True

    # Check Embedding Service
    try:
        req = Request(f"{Config.SERVICES.EMBEDDING_URL}/health", method="GET")
        with urlopen(req, timeout=2) as response:
            services_status["embedding"] = "healthy"
    except Exception:
        services_status["embedding"] = "unhealthy"
        overall_healthy = False

    # Check Cache Service
    try:
        req = Request(f"{Config.SERVICES.CACHE_URL}/health", method="GET")
        with urlopen(req, timeout=2) as response:
            services_status["cache"] = "healthy"
    except Exception:
        services_status["cache"] = "unhealthy"
        overall_healthy = False

    # Check Small LLM Service
    try:
        req = Request(f"{Config.SERVICES.SMALL_LLM_URL}/health", method="GET")
        with urlopen(req, timeout=2) as response:
            services_status["small_llm"] = "healthy"
    except Exception:
        services_status["small_llm"] = "unhealthy"
        overall_healthy = False

    # Check Large LLM Service
    try:
        req = Request(f"{Config.SERVICES.LARGE_LLM_URL}/health", method="GET")
        with urlopen(req, timeout=2) as response:
            services_status["large_llm"] = "healthy"
    except Exception:
        services_status["large_llm"] = "unhealthy"
        overall_healthy = False

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "service": "answer_retrieval",
        "dependencies": services_status,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/logs/{request_id}")
async def get_logs(request_id: str):
    """Get logs for a specific request ID"""
    logs = get_logs_by_request_id(request_id)
    return {"request_id": request_id, "logs": logs, "count": len(logs)}


@app.post("/retrieve-answer", response_model=RetrieveAnswerResponse)
async def retrieve_answer(
    request: RetrieveAnswerRequest, fastapi_request: FastAPIRequest
) -> RetrieveAnswerResponse:
    """
    Orchestrates the complete answer retrieval flow:
    1. Embed query
    2. Search cache for similar Q&A pairs
    3. Try Small LLM with cached context
    4. If no exact match, call Large LLM
    5. Save Large LLM answer to cache

    Args:
        request: RetrieveAnswerRequest with user query
        fastapi_request: FastAPI request object

    Returns:
        RetrieveAnswerResponse with answer and metadata

    Raises:
        HTTPException: If any service fails
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    try:
        logger.info(
            "Starting answer retrieval",
            context={"query": request.query[:100]},
            request_id=request_id,
        )

        # Step 1: Embed the query
        embedding = await _embed_query(request.query, request_id)

        # Step 2: Search cache for similar Q&A pairs
        cached_results = await _search_cache(embedding, request_id)

        # Step 3: Try Small LLM with cached results
        small_llm_response = await _query_small_llm(
            request.query, cached_results, request_id
        )

        # Step 4: Decision point - check if exact match
        if (
            small_llm_response.get("is_exact_match")
            and small_llm_response.get("answer") is not None
        ):
            # Exact match found, return Small LLM answer
            # Record cache hit
            answer_retrieval_cache_hits_total.inc()

            # Record confidence if available
            confidence = small_llm_response.get("confidence")
            if confidence is not None:
                answer_retrieval_confidence.observe(confidence)

            logger.info(
                "Answer retrieval completed (exact match)",
                context={
                    "source": "small_llm",
                    "used_cache": True,
                    "confidence": confidence,
                },
                request_id=request_id,
            )
            return RetrieveAnswerResponse(
                answer=small_llm_response["answer"],
                source="small_llm",
                used_cache=True,
                confidence=confidence,
            )

        # Step 5: No exact match - call Large LLM
        # Record cache miss and large LLM call
        answer_retrieval_cache_misses_total.inc()
        answer_retrieval_llm_calls_total.labels(llm_service="large_llm").inc()

        large_llm_answer = await _query_large_llm(request.query, request_id)

        # Step 6: Save Large LLM answer to cache
        await _save_to_cache(request.query, large_llm_answer, embedding, request_id)

        # Step 7: Return Large LLM response
        logger.info(
            "Answer retrieval completed (large LLM)",
            context={
                "source": "large_llm",
                "used_cache": False,
            },
            request_id=request_id,
        )
        return RetrieveAnswerResponse(
            answer=large_llm_answer,
            source="large_llm",
            used_cache=False,
            confidence=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Answer retrieval failed",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(status_code=500, detail=f"Answer retrieval error: {str(e)}")


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
    try:
        logger.info(
            "Calling Embedding service",
            context={"query_length": len(query)},
            request_id=request_id,
        )

        req = Request(
            f"{Config.SERVICES.EMBEDDING_URL}/embed",
            data=json.dumps({"text": query}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            logger.info(
                "Embedding service responded",
                context={"embedding_dimension": len(result["embedding"])},
                request_id=request_id,
            )
            return result["embedding"]

    except (HTTPError, URLError) as e:
        logger.error(
            "Embedding service failed",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503, detail=f"Embedding service unavailable: {str(e)}"
        )


async def _search_cache(embedding: list[float], request_id: str) -> list[dict]:
    """
    Search cache for similar Q&A pairs

    Args:
        embedding: Query embedding vector
        request_id: Request ID for distributed tracing

    Returns:
        List of similar cached Q&A pairs

    Raises:
        HTTPException: If cache service fails
    """
    try:
        logger.info(
            "Calling Cache service",
            context={"top_k": Config.CACHE_TOP_K},
            request_id=request_id,
        )

        req = Request(
            f"{Config.SERVICES.CACHE_URL}/search",
            data=json.dumps(
                {"embedding": embedding, "top_k": Config.CACHE_TOP_K}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            results = result.get("results", [])
            logger.info(
                "Cache service responded",
                context={"results_count": len(results)},
                request_id=request_id,
            )
            return results

    except (HTTPError, URLError) as e:
        # Cache failure is non-critical, return empty results
        logger.warning(
            "Cache service failed (non-critical)",
            context={"error": str(e), "error_type": type(e).__name__},
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
    try:
        # Check for exact match in cached results (similarity >= 0.95)
        if cached_results:
            for cached in cached_results:
                if cached.get("similarity_score", 0) >= 0.95:
                    # Found exact match, return cached answer
                    logger.info(
                        "Exact match found in cache",
                        context={"similarity_score": cached["similarity_score"]},
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
            "Calling Small LLM service",
            context={
                "has_cached_context": len(cached_results) > 0,
                "cached_count": len(cached_results),
            },
            request_id=request_id,
        )

        # Call Small LLM with OpenAI format
        req = Request(
            f"{Config.SERVICES.SMALL_LLM_URL}/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "deepseek-r1:7b",
                    "messages": messages,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            answer = result["choices"][0]["message"]["content"]

            # Determine confidence based on whether we had cached context
            confidence = 0.7 if cached_results else 0.5

            # Record small LLM call
            answer_retrieval_llm_calls_total.labels(llm_service="small_llm").inc()

            # Record confidence
            answer_retrieval_confidence.observe(confidence)

            logger.info(
                "Small LLM service responded",
                context={
                    "answer_length": len(answer),
                    "confidence": confidence,
                    "is_exact_match": False,
                },
                request_id=request_id,
            )

            return {
                "answer": answer,
                "confidence": confidence,
                "is_exact_match": False,
            }

    except (HTTPError, URLError) as e:
        logger.error(
            "Small LLM service failed",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503, detail=f"Small LLM service unavailable: {str(e)}"
        )


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
    try:
        logger.info(
            "Calling Large LLM service",
            context={"query_length": len(query)},
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

        req = Request(
            f"{Config.SERVICES.LARGE_LLM_URL}/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "gpt-4o-mini",
                    "messages": messages,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            answer = result["choices"][0]["message"]["content"]
            logger.info(
                "Large LLM service responded",
                context={"answer_length": len(answer)},
                request_id=request_id,
            )
            return answer

    except (HTTPError, URLError) as e:
        logger.error(
            "Large LLM service failed",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503, detail=f"Large LLM service unavailable: {str(e)}"
        )


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
    try:
        logger.info(
            "Saving to Cache service",
            context={"query_length": len(query), "answer_length": len(answer)},
            request_id=request_id,
        )

        req = Request(
            f"{Config.SERVICES.CACHE_URL}/save",
            data=json.dumps(
                {"question": query, "answer": answer, "embedding": embedding}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            # Successfully saved (or acknowledged in stub mode)
            logger.info(
                "Cache service save successful",
                context={},
                request_id=request_id,
            )

    except (HTTPError, URLError) as e:
        # Cache save failure is non-critical, silently continue
        logger.warning(
            "Cache service save failed (non-critical)",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8008)
