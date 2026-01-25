import json
import time
import uuid
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
    gateway_cache_hits_total,
    gateway_cache_misses_total,
    gateway_cache_save_duration_seconds,
    gateway_cache_search_duration_seconds,
    gateway_confidence,
    gateway_embedding_duration_seconds,
    gateway_errors_total,
    gateway_input_processor_duration_seconds,
    gateway_large_llm_duration_seconds,
    gateway_llm_calls_total,
    gateway_reformulator_duration_seconds,
    gateway_small_llm_duration_seconds,
    http_request_duration_seconds,
    http_requests_total,
)
from src.models.schemas import (
    ChatCompletionChoice,
    ChatCompletionMessageResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Model,
    ModelListResponse,
)

app = FastAPI(title="Math Tutor API Gateway")
logger = StructuredLogger("gateway")


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Middleware to log all HTTP requests and responses, and record metrics"""
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
                service="gateway",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="gateway",
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
                service="gateway",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="gateway",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

            gateway_errors_total.labels(error_type=type(e).__name__).inc()

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


def check_service_health(service_name: str, service_url: str) -> dict:
    """Check health of a single service"""
    try:
        req = Request(
            f"{service_url}/health",
            method="GET",
        )
        with urlopen(req, timeout=2) as response:
            result = json.loads(response.read().decode("utf-8"))
            service_status = result.get("status", "healthy")
            return {"status": service_status, "details": result}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/health")
async def health():
    """Health check endpoint - checks all individual services"""
    services = {
        "input_processor": Config.SERVICES.INPUT_PROCESSOR_URL,
        "reformulator": Config.SERVICES.REFORMULATOR_URL,
        "embedding": Config.SERVICES.EMBEDDING_URL,
        "cache": Config.SERVICES.CACHE_URL,
        "small_llm": Config.SERVICES.SMALL_LLM_URL,
        "large_llm": Config.SERVICES.LARGE_LLM_URL,
    }

    service_health = {}
    all_healthy = True

    for service_name, service_url in services.items():
        health_status = check_service_health(service_name, service_url)
        service_health[service_name] = health_status
        if health_status["status"] != "healthy":
            all_healthy = False

    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": "gateway",
        "services": service_health,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/track/{request_id}")
async def track_request(request_id: str):
    """
    Track a request across all services by its request ID.

    Returns logs from all services that contain this request ID,
    providing a complete trace of the request's journey through the system.
    """
    all_services = {
        "gateway": Config.SERVICES.GATEWAY_URL,
        "input-processor": Config.SERVICES.INPUT_PROCESSOR_URL,
        "reformulator": Config.SERVICES.REFORMULATOR_URL,
        "embedding": Config.SERVICES.EMBEDDING_URL,
        "cache": Config.SERVICES.CACHE_URL,
        "small-llm": Config.SERVICES.SMALL_LLM_URL,
        "large-llm": Config.SERVICES.LARGE_LLM_URL,
        "fine-tuned-model": Config.SERVICES.FINE_TUNED_MODEL_URL,
    }

    trace = {
        "request_id": request_id,
        "services": {},
        "timeline": [],
    }

    # Get logs from gateway (current service)
    gateway_logs = get_logs_by_request_id(request_id)
    if gateway_logs:
        trace["services"]["gateway"] = {
            "log_count": len(gateway_logs),
            "logs": gateway_logs,
        }
        for log in gateway_logs:
            trace["timeline"].append({"service": "gateway", "log": log})

    # Query each service for logs with this request ID
    for service_name, service_url in all_services.items():
        if service_name == "gateway":
            continue  # Already added above

        try:
            req = Request(
                f"{service_url}/logs/{request_id}",
                method="GET",
            )

            with urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
                logs = result.get("logs", [])

                if logs:
                    trace["services"][service_name] = {
                        "log_count": len(logs),
                        "logs": logs,
                    }

                    for log in logs:
                        trace["timeline"].append({"service": service_name, "log": log})

        except Exception:
            # Service doesn't have the /logs endpoint or is unreachable
            continue

    # Sort timeline chronologically by extracting timestamp from log line
    trace["timeline"].sort(key=lambda x: x["log"][:23])  # Sort by timestamp prefix

    return trace


@app.get("/v1/models", response_model=ModelListResponse)
async def list_models():
    """
    OpenAI-compatible models list endpoint.
    Returns the available model(s) for Open WebUI.
    """
    return ModelListResponse(
        data=[
            Model(
                id="math-tutor",
                created=int(time.time()),
                owned_by="lebanese-high-school-math-tutor",
            )
        ]
    )


async def _process_input(input_text: str, input_type: str, request_id: str) -> dict:
    """
    Call Input Processor to process raw user input

    Args:
        input_text: Raw user input (text or image data)
        input_type: Type of input ('text' or 'image')
        request_id: Request ID for tracing

    Returns:
        Dict with processed_input, input_type, and metadata

    Raises:
        HTTPException: If input processor service fails
    """
    start_time = time.time()
    try:
        logger.info(
            "Phase 1.1: Calling Input Processor",
            context={"input_type": input_type, "input_length": len(input_text)},
            request_id=request_id,
        )

        req = Request(
            f"{Config.SERVICES.INPUT_PROCESSOR_URL}/process",
            data=json.dumps({"input": input_text, "type": input_type}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            duration = time.time() - start_time
            gateway_input_processor_duration_seconds.observe(duration)

            logger.info(
                "Input Processor responded",
                context={
                    "processed_input": result.get("processed_input", "")[:100],
                    "duration_seconds": round(duration, 3),
                },
                request_id=request_id,
            )
            return result

    except (HTTPError, URLError) as e:
        duration = time.time() - start_time
        gateway_input_processor_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="input_processor_error").inc()

        logger.error(
            "Input Processor service error",
            context={"error": str(e), "duration_seconds": round(duration, 3)},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503, detail=f"Input processor service unavailable: {str(e)}"
        )


async def _reformulate_query(
    processed_input: str, input_type: str, request_id: str
) -> dict:
    """
    Call Reformulator to improve query clarity

    Args:
        processed_input: Processed user input from Input Processor
        input_type: Type of input ('text' or 'image')
        request_id: Request ID for tracing

    Returns:
        Dict with reformulated_query, original_input, and improvements_made

    Raises:
        HTTPException: If reformulator service fails
    """
    start_time = time.time()
    try:
        logger.info(
            "Phase 1.2: Calling Reformulator",
            context={"processed_input": processed_input[:100]},
            request_id=request_id,
        )

        req = Request(
            f"{Config.SERVICES.REFORMULATOR_URL}/reformulate",
            data=json.dumps(
                {"processed_input": processed_input, "input_type": input_type}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            duration = time.time() - start_time
            gateway_reformulator_duration_seconds.observe(duration)

            logger.info(
                "Reformulator responded",
                context={
                    "reformulated_query": result.get("reformulated_query", "")[:100],
                    "improvements_made": result.get("improvements_made", []),
                    "duration_seconds": round(duration, 3),
                },
                request_id=request_id,
            )
            return result

    except (HTTPError, URLError) as e:
        duration = time.time() - start_time
        gateway_reformulator_duration_seconds.observe(duration)
        gateway_errors_total.labels(error_type="reformulator_error").inc()

        logger.error(
            "Reformulator service error",
            context={"error": str(e), "duration_seconds": round(duration, 3)},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503, detail=f"Reformulator service unavailable: {str(e)}"
        )


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

        req = Request(
            f"{Config.SERVICES.EMBEDDING_URL}/embed",
            data=json.dumps({"text": query}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
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

    except (HTTPError, URLError) as e:
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
        HTTPException: If cache service fails (non-critical)
    """
    start_time = time.time()
    try:
        logger.info(
            "Phase 2.2: Calling Cache service",
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

    except (HTTPError, URLError) as e:
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

    except (HTTPError, URLError) as e:
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
    start_time = time.time()
    try:
        logger.info(
            "Phase 2.5: Saving to Cache service",
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


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest, fastapi_request: FastAPIRequest
):
    """
    OpenAI-compatible chat completions endpoint - orchestrates the complete pipeline.

    Flow:
    1. Extract last user message from conversation
    2. Phase 1 (Data Processing): Process and reformulate user input
       - Input Processor → Reformulator
    3. Phase 2 (Answer Retrieval): Get answer using cache and LLMs
       - Embedding → Cache → Small LLM → [conditional] Large LLM → Save
    4. Return answer in OpenAI format

    Returns OpenAI-compatible chat completion response.
    """
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    try:
        # Extract last user message from messages array
        user_message = next(
            (msg.content for msg in reversed(request.messages) if msg.role == "user"),
            None,
        )

        if not user_message:
            logger.warning(
                "No user message in request",
                context={"messages_count": len(request.messages)},
                request_id=request_id,
            )
            raise HTTPException(
                status_code=400,
                detail="No user message found in request",
            )

        logger.info(
            "Starting chat completion pipeline",
            context={
                "model": request.model,
                "user_message": user_message[:100],
                "message_count": len(request.messages),
            },
            request_id=request_id,
        )

        # ===== PHASE 1: DATA PROCESSING =====
        logger.info(
            "PHASE 1: Data Processing - Starting",
            context={},
            request_id=request_id,
        )

        # Step 1.1: Process input
        input_result = await _process_input(user_message, "text", request_id)
        processed_input = input_result["processed_input"]

        # Step 1.2: Reformulate query
        reformulate_result = await _reformulate_query(
            processed_input, "text", request_id
        )
        reformulated_query = reformulate_result["reformulated_query"]

        logger.info(
            "PHASE 1: Data Processing - Completed",
            context={
                "original_input": user_message[:100],
                "reformulated_query": reformulated_query[:100],
                "improvements_made": reformulate_result.get("improvements_made", []),
            },
            request_id=request_id,
        )

        # ===== PHASE 2: ANSWER RETRIEVAL =====
        logger.info(
            "PHASE 2: Answer Retrieval - Starting",
            context={"query": reformulated_query[:100]},
            request_id=request_id,
        )

        # Step 2.1: Embed the query
        embedding = await _embed_query(reformulated_query, request_id)

        # Step 2.2: Search cache for similar Q&A pairs
        cached_results = await _search_cache(embedding, request_id)

        # Step 2.3: Try Small LLM with cached results (or use exact match if found)
        small_llm_response = await _query_small_llm(
            reformulated_query, cached_results, request_id
        )

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

            logger.info(
                "Chat completion pipeline successful",
                context={
                    "total_answer_length": len(answer),
                    "source": "cache_exact_match",
                },
                request_id=request_id,
            )

            return ChatCompletionResponse(
                id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
                created=int(time.time()),
                model=request.model,
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatCompletionMessageResponse(content=answer),
                        finish_reason="stop",
                    )
                ],
            )

        # Step 2.5: No exact match - call Large LLM
        # Record cache miss and large LLM call
        gateway_cache_misses_total.inc()

        large_llm_answer = await _query_large_llm(reformulated_query, request_id)

        # Step 2.6: Save Large LLM answer to cache
        await _save_to_cache(
            reformulated_query, large_llm_answer, embedding, request_id
        )

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

        logger.info(
            "Chat completion pipeline successful",
            context={
                "total_answer_length": len(large_llm_answer),
                "source": "large_llm",
            },
            request_id=request_id,
        )

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionMessageResponse(content=large_llm_answer),
                    finish_reason="stop",
                )
            ],
        )

    except HTTPException:
        raise
    except KeyError as e:
        logger.error(
            "Unexpected response format",
            context={"missing_key": str(e)},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected response format from service: missing key {str(e)}",
        )
    except Exception as e:
        logger.error(
            "Internal error in chat completion",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
