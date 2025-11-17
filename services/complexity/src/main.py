import re

from fastapi import FastAPI
from src.config import Config
from src.models.schemas import ComplexityRequest, ComplexityResponse

app = FastAPI(title="Math Tutor Complexity Assessment Service")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "complexity",
        "threshold": Config.COMPLEXITY_THRESHOLD,
    }


def assess_complexity(query: str) -> tuple[float, str]:
    """
    Assess the complexity of a math question using heuristics.

    Returns:
        tuple: (complexity_score, reasoning)
    """
    score = 0.0
    reasons = []

    query_lower = query.lower()

    # Check for advanced math topics (higher complexity)
    advanced_topics = [
        "integral",
        "derivative",
        "differential equation",
        "partial derivative",
        "multivariable",
        "series",
        "convergence",
        "limit",
        "taylor",
        "fourier",
        "laplace",
        "matrix",
        "eigenvalue",
        "eigenvector",
        "proof",
        "theorem",
    ]

    for topic in advanced_topics:
        if topic in query_lower:
            score += 0.3
            reasons.append(f"Contains advanced topic: {topic}")
            break

    # Check for equation complexity
    if re.search(r"\^[3-9]|\^\{[0-9]{2,}\}", query):
        score += 0.2
        reasons.append("Contains high-degree polynomials")

    # Check for multiple variables
    var_pattern = r"[a-z]\s*="
    var_matches = re.findall(var_pattern, query_lower)
    if len(var_matches) >= 3:
        score += 0.2
        reasons.append("Multiple variables detected")

    # Check for word problem indicators (can be complex)
    word_problem_indicators = [
        "if",
        "find",
        "calculate",
        "determine",
        "prove",
        "show that",
        "given that",
    ]
    if any(indicator in query_lower for indicator in word_problem_indicators):
        score += 0.1
        reasons.append("Word problem structure")

    # Check query length (longer queries might be more complex)
    if len(query) > 200:
        score += 0.15
        reasons.append("Long query length")
    elif len(query) > 100:
        score += 0.05

    # Check for multi-step problems
    multi_step_indicators = ["step", "then", "next", "and", "also"]
    if sum(1 for ind in multi_step_indicators if ind in query_lower) >= 2:
        score += 0.15
        reasons.append("Multi-step problem")

    # Check for basic operations (lower complexity)
    basic_ops = ["add", "subtract", "multiply", "divide", "+", "-", "*", "/"]
    if any(op in query_lower for op in basic_ops) and score == 0:
        score = 0.1
        reasons.append("Basic arithmetic operations")

    # Normalize score to 0-1 range
    score = min(score, 1.0)

    if not reasons:
        reasons.append("Simple query with no complex indicators")
        score = 0.1

    reasoning = "; ".join(reasons)
    return score, reasoning


@app.post("/assess", response_model=ComplexityResponse)
async def assess_query_complexity(request: ComplexityRequest):
    """
    Assess the complexity of a math query.

    This endpoint analyzes the query using heuristics to determine
    whether it should be routed to a large or small LLM.

    Args:
        request: ComplexityRequest containing the query

    Returns:
        ComplexityResponse with complexity score and routing decision
    """
    complexity_score, reasoning = assess_complexity(request.query)

    is_complex = complexity_score >= Config.COMPLEXITY_THRESHOLD

    return ComplexityResponse(
        complexity_score=complexity_score,
        is_complex=is_complex,
        reasoning=reasoning,
    )
