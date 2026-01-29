import re
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from src.config import Config
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

# CORS for UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Ollama client (OpenAI-compatible API)
ollama_client: Optional[OpenAI] = None

try:
    ollama_client = OpenAI(
        base_url=f"{Config.OLLAMA.SERVICE_URL}/v1",
        api_key="ollama",  # Ollama doesn't need a real key
    )
except Exception:
    ollama_client = None


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
        r"\?\s*$",  # Ends with question mark
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

    # If only one intent matched, high confidence
    if len(matches) == 1:
        intent = list(matches.keys())[0]
        return intent, 0.95, matches[intent]

    # Multiple matches - pick the one with most pattern hits
    best_intent = max(matches, key=lambda k: len(matches[k]))
    total_matches = sum(len(v) for v in matches.values())
    best_matches = len(matches[best_intent])
    confidence = best_matches / total_matches * 0.8  # Cap at 0.8 for ambiguous

    return best_intent, confidence, matches[best_intent]


def classify_llm_based(text: str, context: Optional[str] = None) -> IntentCategory:
    """Classify using LLM (Ollama)"""
    if not ollama_client:
        raise HTTPException(status_code=503, detail="Ollama not available")

    prompt = Config.CLASSIFICATION_PROMPT.format(response=text)
    if context:
        prompt = f'Tutor\'s question: "{context}"\n\n{prompt}'

    response = ollama_client.chat.completions.create(
        model=Config.OLLAMA.MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=50,
    )

    content = response.choices[0].message.content
    if not content:
        return IntentCategory.OFF_TOPIC
    result = content.strip().upper()

    # Extract intent from response (handle thinking tags if present)
    # DeepSeek-R1 might include <think> tags
    if "</think>" in result:
        result = result.split("</think>")[-1].strip()

    # Map to enum
    intent_map = {
        "AFFIRMATIVE": IntentCategory.AFFIRMATIVE,
        "NEGATIVE": IntentCategory.NEGATIVE,
        "PARTIAL": IntentCategory.PARTIAL,
        "QUESTION": IntentCategory.QUESTION,
        "SKIP": IntentCategory.SKIP,
        "OFF_TOPIC": IntentCategory.OFF_TOPIC,
    }

    for key, value in intent_map.items():
        if key in result:
            return value

    return IntentCategory.OFF_TOPIC


def classify_text(
    text: str, context: Optional[str] = None
) -> tuple[IntentCategory, float, ClassificationMethod, Optional[list[str]]]:
    """
    Hybrid classification: rule-based first, LLM fallback for low confidence.
    """
    # Try rule-based first
    intent, confidence, patterns = classify_rule_based(text)

    if intent and confidence >= Config.CLASSIFIER.RULE_CONFIDENCE_THRESHOLD:
        return intent, confidence, ClassificationMethod.RULE_BASED, patterns

    # If rule-based is uncertain, try LLM
    if Config.CLASSIFIER.USE_LLM_FALLBACK and ollama_client:
        try:
            llm_intent = classify_llm_based(text, context)

            if intent and intent == llm_intent:
                # Rule and LLM agree - boost confidence
                return intent, 0.9, ClassificationMethod.HYBRID, patterns
            elif intent:
                # Disagree - trust LLM but lower confidence
                return llm_intent, 0.7, ClassificationMethod.HYBRID, None
            else:
                # No rule match - use LLM result
                return llm_intent, 0.8, ClassificationMethod.LLM_BASED, None
        except Exception:
            pass  # Fall through to rule-based or default

    # Return rule-based result or default
    if intent:
        return intent, confidence, ClassificationMethod.RULE_BASED, patterns

    return IntentCategory.OFF_TOPIC, 0.3, ClassificationMethod.RULE_BASED, None


# === Endpoints ===


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint"""
    ollama_available = False
    if ollama_client:
        try:
            # Quick check if Ollama is reachable
            ollama_client.models.list()
            ollama_available = True
        except Exception:
            pass

    return HealthResponse(
        status="healthy",
        service="intent_classifier",
        ollama_available=ollama_available,
        model_name=Config.OLLAMA.MODEL_NAME,
    )


@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest) -> ClassifyResponse:
    """Classify user intent from text"""
    intent, confidence, method, patterns = classify_text(request.text, request.context)

    return ClassifyResponse(
        intent=intent,
        confidence=confidence,
        method=method,
        matched_patterns=patterns,
    )


@app.post("/classify/batch", response_model=BatchClassifyResponse)
async def classify_batch(request: BatchClassifyRequest) -> BatchClassifyResponse:
    """Classify multiple texts"""
    results = []
    for text in request.texts:
        intent, confidence, method, patterns = classify_text(text, request.context)
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
async def classify_rule_only(request: ClassifyRequest) -> ClassifyResponse:
    """Classify using only rule-based matching (faster, no LLM)"""
    intent, confidence, patterns = classify_rule_based(request.text)

    if not intent:
        intent = IntentCategory.OFF_TOPIC
        confidence = 0.3

    return ClassifyResponse(
        intent=intent,
        confidence=confidence,
        method=ClassificationMethod.RULE_BASED,
        matched_patterns=patterns if patterns else None,
    )
