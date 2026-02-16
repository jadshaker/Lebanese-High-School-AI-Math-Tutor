import re
from typing import Optional

from src.clients.llm import small_llm_client
from src.config import Config
from src.logging_utils import StructuredLogger
from src.metrics import (
    classification_confidence,
    classification_method_total,
    classifications_total,
    llm_fallback_errors_total,
    llm_fallback_total,
)
from src.models.schemas import (
    ClassificationMethod,
    ClassifyResponse,
    IntentCategory,
)
from src.services.intent_classifier.prompts import (
    CLASSIFICATION_PROMPT,
    INTENT_PATTERNS,
)

logger = StructuredLogger("intent_classifier")


def classify_rule_based(
    text: str,
) -> tuple[Optional[IntentCategory], float, list[str]]:
    """Classify using pattern matching."""
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
    """Classify using Small LLM."""
    prompt = CLASSIFICATION_PROMPT.format(response=text)
    if context:
        prompt = f'Tutor\'s question: "{context}"\n\n{prompt}'

    logger.info(
        "Calling Small LLM for classification",
        context={"text_length": len(text)},
        request_id=request_id,
    )

    llm_fallback_total.inc()

    try:
        response = small_llm_client.chat.completions.create(
            model=Config.SMALL_LLM.MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=Config.CLASSIFIER.LLM_TEMPERATURE,
            max_tokens=Config.CLASSIFIER.LLM_MAX_TOKENS,
        )

        content = response.choices[0].message.content
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
) -> ClassifyResponse:
    """
    Hybrid classification: rule-based first, LLM fallback for low confidence.
    Returns ClassifyResponse with intent, confidence, method, patterns.
    """
    intent, confidence, patterns = classify_rule_based(text)

    if intent and confidence >= Config.CLASSIFIER.RULE_CONFIDENCE_THRESHOLD:
        result = ClassifyResponse(
            intent=intent,
            confidence=confidence,
            method=ClassificationMethod.RULE_BASED,
            matched_patterns=patterns,
        )
    elif Config.CLASSIFIER.USE_LLM_FALLBACK:
        try:
            llm_intent = classify_llm_based(text, context, request_id)

            if intent and intent == llm_intent:
                result = ClassifyResponse(
                    intent=intent,
                    confidence=0.9,
                    method=ClassificationMethod.HYBRID,
                    matched_patterns=patterns,
                )
            elif intent:
                result = ClassifyResponse(
                    intent=llm_intent,
                    confidence=0.7,
                    method=ClassificationMethod.HYBRID,
                    matched_patterns=None,
                )
            else:
                result = ClassifyResponse(
                    intent=llm_intent,
                    confidence=0.8,
                    method=ClassificationMethod.LLM_BASED,
                    matched_patterns=None,
                )
        except Exception:
            if intent:
                result = ClassifyResponse(
                    intent=intent,
                    confidence=confidence,
                    method=ClassificationMethod.RULE_BASED,
                    matched_patterns=patterns,
                )
            else:
                result = ClassifyResponse(
                    intent=IntentCategory.OFF_TOPIC,
                    confidence=0.3,
                    method=ClassificationMethod.RULE_BASED,
                    matched_patterns=None,
                )
    elif intent:
        result = ClassifyResponse(
            intent=intent,
            confidence=confidence,
            method=ClassificationMethod.RULE_BASED,
            matched_patterns=patterns,
        )
    else:
        result = ClassifyResponse(
            intent=IntentCategory.OFF_TOPIC,
            confidence=0.3,
            method=ClassificationMethod.RULE_BASED,
            matched_patterns=None,
        )

    # Record metrics
    classifications_total.labels(intent=result.intent.value).inc()
    classification_method_total.labels(method=result.method.value).inc()
    classification_confidence.observe(result.confidence)

    return result
