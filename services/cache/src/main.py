from fastapi import FastAPI
from src.models.schemas import (
    CachedResult,
    SaveRequest,
    SaveResponse,
    SearchRequest,
    SearchResponse,
    TutoringRequest,
    TutoringResponse,
)

app = FastAPI(title="Math Tutor Cache Service (Stub)")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "cache",
        "mode": "stub",
        "message": "Cache service running in stub mode - returns dummy data",
    }


@app.post("/search", response_model=SearchResponse)
async def search_similar(request: SearchRequest):
    """
    Search for similar Q&A pairs in cache (STUB).

    This is a stub implementation that returns dummy similar questions.
    In the full implementation, this will perform cosine similarity search
    on the vector database.

    Args:
        request: SearchRequest with embedding vector and top_k

    Returns:
        SearchResponse with dummy similar Q&A pairs
    """
    # Stub: Return dummy similar questions
    dummy_results = [
        CachedResult(
            question="What is the derivative of x^3?",
            answer="[Cached] The derivative of x^3 is 3x^2. Using the power rule, we bring down the exponent and reduce it by 1.",
            similarity_score=0.85,
        ),
        CachedResult(
            question="How do you find the derivative of a polynomial?",
            answer="[Cached] To find the derivative of a polynomial, apply the power rule to each term: d/dx(x^n) = nx^(n-1).",
            similarity_score=0.72,
        ),
        CachedResult(
            question="What is the chain rule in calculus?",
            answer="[Cached] The chain rule states that d/dx[f(g(x))] = f'(g(x)) * g'(x). It's used for composite functions.",
            similarity_score=0.68,
        ),
    ]

    # Return only top_k results
    results = dummy_results[: request.top_k]

    return SearchResponse(results=results, count=len(results))


@app.post("/save", response_model=SaveResponse)
async def save_answer(request: SaveRequest):
    """
    Save Q&A pair to cache (STUB).

    This is a stub implementation that acknowledges the save request
    but doesn't actually store anything. In the full implementation,
    this will save to a vector database.

    Args:
        request: SaveRequest with question, answer, and embedding

    Returns:
        SaveResponse acknowledging the save (but not actually saving)
    """
    return SaveResponse(
        status="success",
        message=f"Answer saved (stub mode - not actually stored). Question length: {len(request.question)} chars, Embedding dimensions: {len(request.embedding)}",
    )


@app.post("/tutoring", response_model=TutoringResponse)
async def check_tutoring_cache(request: TutoringRequest):
    """
    Check tutoring cache for question (STUB - Phase 3).

    This is a stub implementation for Phase 3 tutoring cache.
    Always returns not found. Full implementation planned for later.

    Args:
        request: TutoringRequest with question

    Returns:
        TutoringResponse indicating no data found
    """
    return TutoringResponse(
        found=False,
        data=None,
    )
