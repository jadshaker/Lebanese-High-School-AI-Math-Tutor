import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from src.config import Config
from src.models.schemas import RetrieveAnswerRequest, RetrieveAnswerResponse

app = FastAPI(title="Answer Retrieval Service", version="1.0.0")


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


@app.post("/retrieve-answer", response_model=RetrieveAnswerResponse)
async def retrieve_answer(request: RetrieveAnswerRequest) -> RetrieveAnswerResponse:
    """
    Orchestrates the complete answer retrieval flow:
    1. Embed query
    2. Search cache for similar Q&A pairs
    3. Try Small LLM with cached context
    4. If no exact match, call Large LLM
    5. Save Large LLM answer to cache

    Args:
        request: RetrieveAnswerRequest with user query

    Returns:
        RetrieveAnswerResponse with answer and metadata

    Raises:
        HTTPException: If any service fails
    """
    try:
        # Step 1: Embed the query
        embedding = await _embed_query(request.query)

        # Step 2: Search cache for similar Q&A pairs
        cached_results = await _search_cache(embedding)

        # Step 3: Try Small LLM with cached results
        small_llm_response = await _query_small_llm(request.query, cached_results)

        # Step 4: Decision point - check if exact match
        if (
            small_llm_response.get("is_exact_match")
            and small_llm_response.get("answer") is not None
        ):
            # Exact match found, return Small LLM answer
            return RetrieveAnswerResponse(
                answer=small_llm_response["answer"],
                source="small_llm",
                used_cache=True,
                confidence=small_llm_response.get("confidence"),
            )

        # Step 5: No exact match - call Large LLM
        large_llm_answer = await _query_large_llm(request.query)

        # Step 6: Save Large LLM answer to cache
        await _save_to_cache(request.query, large_llm_answer, embedding)

        # Step 7: Return Large LLM response
        return RetrieveAnswerResponse(
            answer=large_llm_answer,
            source="large_llm",
            used_cache=False,
            confidence=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Answer retrieval error: {str(e)}")


async def _embed_query(query: str) -> list[float]:
    """
    Call Embedding Service to convert query to vector

    Args:
        query: User's question text

    Returns:
        Embedding vector as list of floats

    Raises:
        HTTPException: If embedding service fails
    """
    try:
        req = Request(
            f"{Config.SERVICES.EMBEDDING_URL}/embed",
            data=json.dumps({"text": query}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["embedding"]

    except (HTTPError, URLError) as e:
        raise HTTPException(
            status_code=503, detail=f"Embedding service unavailable: {str(e)}"
        )


async def _search_cache(embedding: list[float]) -> list[dict]:
    """
    Search cache for similar Q&A pairs

    Args:
        embedding: Query embedding vector

    Returns:
        List of similar cached Q&A pairs

    Raises:
        HTTPException: If cache service fails
    """
    try:
        req = Request(
            f"{Config.SERVICES.CACHE_URL}/search",
            data=json.dumps(
                {"embedding": embedding, "top_k": Config.CACHE_TOP_K}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("results", [])

    except (HTTPError, URLError):
        # Cache failure is non-critical, return empty results
        return []


async def _query_small_llm(query: str, cached_results: list[dict]) -> dict:
    """
    Query Small LLM with cached context

    Args:
        query: User's question
        cached_results: Similar cached Q&A pairs

    Returns:
        Dict with answer, confidence, and is_exact_match

    Raises:
        HTTPException: If small LLM service fails
    """
    try:
        # Format cached results for Small LLM
        formatted_cache = (
            [
                {
                    "question": r["question"],
                    "answer": r["answer"],
                    "similarity_score": r["similarity_score"],
                }
                for r in cached_results
            ]
            if cached_results
            else None
        )

        req = Request(
            f"{Config.SERVICES.SMALL_LLM_URL}/query",
            data=json.dumps({"query": query, "cached_results": formatted_cache}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result

    except (HTTPError, URLError) as e:
        raise HTTPException(
            status_code=503, detail=f"Small LLM service unavailable: {str(e)}"
        )


async def _query_large_llm(query: str) -> str:
    """
    Query Large LLM for final answer

    Args:
        query: User's question

    Returns:
        Answer string from Large LLM

    Raises:
        HTTPException: If large LLM service fails
    """
    try:
        req = Request(
            f"{Config.SERVICES.LARGE_LLM_URL}/generate",
            data=json.dumps({"query": query}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["answer"]

    except (HTTPError, URLError) as e:
        raise HTTPException(
            status_code=503, detail=f"Large LLM service unavailable: {str(e)}"
        )


async def _save_to_cache(query: str, answer: str, embedding: list[float]) -> None:
    """
    Save Q&A pair to cache (non-critical operation)

    Args:
        query: User's question
        answer: Final answer
        embedding: Query embedding vector
    """
    try:
        req = Request(
            f"{Config.SERVICES.CACHE_URL}/save",
            data=json.dumps(
                {"question": query, "answer": answer, "embedding": embedding}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(req, timeout=10) as response:
            # Successfully saved (or acknowledged in stub mode)
            pass

    except (HTTPError, URLError):
        # Cache save failure is non-critical, silently continue
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8008)
