import json
import re
import time
from typing import Optional
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
    classification_confidence,
    classification_method_total,
    classifications_total,
    http_request_duration_seconds,
    http_requests_total,
    llm_fallback_errors_total,
    llm_fallback_total,
)
from src.models.schemas import (
    BatchClassifyRequest,
    BatchClassifyResponse,
    ClassificationMethod,
    ClassifyRequest,
    ClassifyResponse,
    HealthResponse,
    IntentCategory,
)

app = FastAPI(title="Math Tutor Intent Classifier Service")
logger = StructuredLogger("intent_classifier")


# === Pattern Definitions for Rule-Based Classification ===

INTENT_PATTERNS: dict[IntentCategory, list[str]] = {
    IntentCategory.AFFIRMATIVE: [
        r"\byes\b",
        r"\byeah\b",
        r"\byep\b",
        r"\byup\b",
        r"\bsure\b",
        r"\bok\b",
        r"\bokay\b",
        r"\bcorrect\b",
        r"\bright\b",
        r"\bexactly\b",
        r"\bi know\b",
        r"\bi understand\b",
        r"\bi got it\b",
        r"\bunderstood\b",
        r"\bof course\b",
        r"\bdefinitely\b",
        r"\babsolutely\b",
        r"\bfamiliar\b",
        r"\bi remember\b",
        r"\blearned\s+(it|that|this)\b",
    ],
    IntentCategory.NEGATIVE: [
        r"\bno\b",
        r"\bnope\b",
        r"\bnah\b",
        r"\bnot\s+really\b",
        r"\bi\s+don'?t\s+know\b",
        r"\bi\s+don'?t\s+understand\b",
        r"\bnever\s+(learned|heard|seen)\b",
        r"\bunfamiliar\b",
        r"\bconfused\b",
        r"\bi\s+forgot\b",
        r"\bcan'?t\s+remember\b",
        r"\bwhat\s+is\s+that\b",
        r"\bi\s+have\s+no\s+idea\b",
        r"\bnot\s+at\s+all\b",
        r"\bdidn'?t\s+learn\b",
    ],
    IntentCategory.PARTIAL: [
        r"\bmaybe\b",
        r"\bsomewhat\b",
        r"\bkind\s+of\b",
        r"\bsort\s+of\b",
        r"\ba\s+little\b",
        r"\bnot\s+sure\b",
        r"\bi\s+think\s+so\b",
        r"\bprobably\b",
        r"\bpartially\b",
        r"\bsomehow\b",
        r"\bi\s+guess\b",
        r"\bbit\s+rusty\b",
        r"\bvaguely\b",
    ],
    IntentCategory.QUESTION: [
        r"\bwhat\s+(do\s+you\s+mean|is|are|does)\b",
        r"\bhow\s+(do|does|is|can)\b",
        r"\bwhy\b",
        r"\bcan\s+you\s+explain\b",
        r"\bcould\s+you\s+(explain|clarify)\b",
        r"\bwhat'?s\s+that\b",
        r"\bi\s+don'?t\s+get\s+it\b",
        r"\bexplain\s+(that|this|more)\b",
        r"\?\s*$",
    ],
    IntentCategory.SKIP: [
        r"\bjust\s+(tell|give|show)\s+me\b",
        r"\bskip\b",
        r"\bgive\s+me\s+the\s+answer\b",
        r"\btell\s+me\s+the\s+answer\b",
        r"\bi\s+just\s+want\s+the\s+answer\b",
        r"\bget\s+to\s+the\s+point\b",
        r"\bno\s+need\s+to\s+explain\b",
        r"\bjust\s+answer\b",
    ],
}


@app.middleware("http")
async def logging_and_metrics_middleware(request: FastAPIRequest, call_next):
    """Middleware to log all HTTP requests and record metrics"""
    incoming_request_id = request.headers.get("X-Request-ID")
    request_id = incoming_request_id if incoming_request_id else generate_request_id()
    start_time = time.time()

    is_metrics_endpoint = request.url.path == "/metrics"

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

    request.state.request_id = request_id

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="intent_classifier",
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service="intent_classifier",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

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

        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as e:
        duration = time.time() - start_time

        if not is_metrics_endpoint:
            http_requests_total.labels(
                service="intent_classifier",
                endpoint=request.url.path,
                method=request.method,
                status=500,
            ).inc()

            http_request_duration_seconds.labels(
                service="intent_classifier",
                endpoint=request.url.path,
                method=request.method,
            ).observe(duration)

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


def classify_rule_based(text: str) -> tuple[Optional[IntentCategory], float, list[str]]:
    """
    Classify using pattern matching.
    Returns (intent, confidence, matched_patterns) or (None, 0, []) if no match.
    """
    text_lower = text.lower().strip()
    matches: dict[IntentCategory, list[str]] = {}

    for intent, patterns in INTENT_PATTERNS.items():
        matched = []
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                matched.append(pattern)
        if matched:
            matches[intent] = matched

    if not matches:
        return None, 0.0, []

    if len(matches) == 1:
        intent = list(matches.keys())[0]
        return intent, 0.95, matches[intent]

    best_intent = max(matches, key=lambda k: len(matches[k]))
    total_matches = sum(len(v) for v in matches.values())
    best_matches = len(matches[best_intent])
    confidence = best_matches / total_matches * 0.8

    return best_intent, confidence, matches[best_intent]


def classify_llm_based(
    text: str, context: Optional[str], request_id: str
) -> IntentCategory:
    """Classify using Small LLM service"""
    prompt = Config.CLASSIFICATION_PROMPT.format(response=text)
    if context:
        prompt = f'Tutor\'s question: "{context}"\n\n{prompt}'

    payload = {
        "model": "math-tutor",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 50,
    }

    logger.info(
        "Calling Small LLM for classification",
        context={"text_length": len(text)},
        request_id=request_id,
    )

    llm_fallback_total.inc()

    try:
        req = Request(
            f"{Config.SERVICES.SMALL_LLM_URL}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Request-ID": request_id},
            method="POST",
        )

        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]

        if not content:
            return IntentCategory.OFF_TOPIC

        result_text = content.strip().upper()

        if "</think>" in result_text:
            result_text = result_text.split("</think>")[-1].strip()

        intent_map = {
            "AFFIRMATIVE": IntentCategory.AFFIRMATIVE,
            "NEGATIVE": IntentCategory.NEGATIVE,
            "PARTIAL": IntentCategory.PARTIAL,
            "QUESTION": IntentCategory.QUESTION,
            "SKIP": IntentCategory.SKIP,
            "OFF_TOPIC": IntentCategory.OFF_TOPIC,
        }

        for key, value in intent_map.items():
            if key in result_text:
                logger.info(
                    "LLM classification result",
                    context={"intent": value.value},
                    request_id=request_id,
                )
                return value

        return IntentCategory.OFF_TOPIC

    except (HTTPError, URLError) as e:
        llm_fallback_errors_total.inc()
        logger.error(
            "LLM classification failed",
            context={"error": str(e)},
            request_id=request_id,
        )
        raise HTTPException(
            status_code=503, detail=f"Small LLM service unavailable: {e}"
        )
    except Exception as e:
        llm_fallback_errors_total.inc()
        logger.error(
            "LLM classification error",
            context={"error": str(e), "error_type": type(e).__name__},
            request_id=request_id,
        )
        return IntentCategory.OFF_TOPIC


def classify_text(
    text: str, context: Optional[str], request_id: str
) -> tuple[IntentCategory, float, ClassificationMethod, Optional[list[str]]]:
    """
    Hybrid classification: rule-based first, LLM fallback for low confidence.
    """
    intent, confidence, patterns = classify_rule_based(text)

    if intent and confidence >= Config.CLASSIFIER.RULE_CONFIDENCE_THRESHOLD:
        return intent, confidence, ClassificationMethod.RULE_BASED, patterns

    if Config.CLASSIFIER.USE_LLM_FALLBACK:
        try:
            llm_intent = classify_llm_based(text, context, request_id)

            if intent and intent == llm_intent:
                return intent, 0.9, ClassificationMethod.HYBRID, patterns
            elif intent:
                return llm_intent, 0.7, ClassificationMethod.HYBRID, None
            else:
                return llm_intent, 0.8, ClassificationMethod.LLM_BASED, None
        except Exception:
            pass

    if intent:
        return intent, confidence, ClassificationMethod.RULE_BASED, patterns

    return IntentCategory.OFF_TOPIC, 0.3, ClassificationMethod.RULE_BASED, None


# === Endpoints ===


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint"""
    small_llm_available = False

    try:
        req = Request(
            f"{Config.SERVICES.SMALL_LLM_URL}/health",
            method="GET",
        )
        with urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
            small_llm_available = result.get("status") == "healthy"
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if small_llm_available else "degraded",
        service="intent_classifier",
        small_llm_available=small_llm_available,
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/logs/{request_id}")
async def get_logs(request_id: str):
    """Get logs for a specific request ID"""
    logs = get_logs_by_request_id(request_id)
    return {"request_id": request_id, "logs": logs, "count": len(logs)}


@app.post("/classify", response_model=ClassifyResponse)
async def classify(
    request: ClassifyRequest, fastapi_request: FastAPIRequest
) -> ClassifyResponse:
    """Classify user intent from text"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    logger.info(
        "Classifying intent",
        context={
            "text_length": len(request.text),
            "has_context": bool(request.context),
        },
        request_id=request_id,
    )

    intent, confidence, method, patterns = classify_text(
        request.text, request.context, request_id
    )

    classifications_total.labels(intent=intent.value).inc()
    classification_method_total.labels(method=method.value).inc()
    classification_confidence.observe(confidence)

    logger.info(
        "Classification complete",
        context={
            "intent": intent.value,
            "confidence": confidence,
            "method": method.value,
        },
        request_id=request_id,
    )

    return ClassifyResponse(
        intent=intent,
        confidence=confidence,
        method=method,
        matched_patterns=patterns,
    )


@app.post("/classify/batch", response_model=BatchClassifyResponse)
async def classify_batch(
    request: BatchClassifyRequest, fastapi_request: FastAPIRequest
) -> BatchClassifyResponse:
    """Classify multiple texts"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    logger.info(
        "Batch classifying intents",
        context={"count": len(request.texts)},
        request_id=request_id,
    )

    results = []
    for text in request.texts:
        intent, confidence, method, patterns = classify_text(
            text, request.context, request_id
        )
        classifications_total.labels(intent=intent.value).inc()
        classification_method_total.labels(method=method.value).inc()
        classification_confidence.observe(confidence)

        results.append(
            ClassifyResponse(
                intent=intent,
                confidence=confidence,
                method=method,
                matched_patterns=patterns,
            )
        )

    return BatchClassifyResponse(results=results)


@app.post("/classify/rule-only", response_model=ClassifyResponse)
async def classify_rule_only(
    request: ClassifyRequest, fastapi_request: FastAPIRequest
) -> ClassifyResponse:
    """Classify using only rule-based matching (faster, no LLM)"""
    request_id = getattr(fastapi_request.state, "request_id", generate_request_id())

    intent, confidence, patterns = classify_rule_based(request.text)

    if not intent:
        intent = IntentCategory.OFF_TOPIC
        confidence = 0.3

    classifications_total.labels(intent=intent.value).inc()
    classification_method_total.labels(method="rule_based").inc()
    classification_confidence.observe(confidence)

    logger.info(
        "Rule-only classification complete",
        context={"intent": intent.value, "confidence": confidence},
        request_id=request_id,
    )

    return ClassifyResponse(
        intent=intent,
        confidence=confidence,
        method=ClassificationMethod.RULE_BASED,
        matched_patterns=patterns if patterns else None,
    )
