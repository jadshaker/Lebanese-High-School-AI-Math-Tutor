import pytest

from tests.unit.test_services.conftest import _ensure_env, _ensure_path, _mock_logging

_ensure_env()
_ensure_path()
_mock_logging()

from src.models.schemas import ClassificationMethod, IntentCategory
from src.services.intent_classifier.service import classify_text


@pytest.mark.unit
def test_classify_affirmative():
    """Test classification of affirmative responses via rule-based matching."""
    test_cases = [
        "yes",
        "Yes, I understand",
        "understood",
        "correct",
        "right",
        "sure",
        "okay",
        "definitely",
    ]

    for text in test_cases:
        result = classify_text(text, None, "req-1")
        assert result.intent == IntentCategory.AFFIRMATIVE, f"Failed for: {text}"
        assert result.method == ClassificationMethod.RULE_BASED
        assert result.confidence >= 0.8


@pytest.mark.unit
def test_classify_negative():
    """Test classification of negative responses via rule-based matching."""
    test_cases = [
        "no",
        "I don't know",
        "I don't understand",
        "I'm confused",
        "not at all",
    ]

    for text in test_cases:
        result = classify_text(text, None, "req-2")
        assert result.intent == IntentCategory.NEGATIVE, f"Failed for: {text}"
        assert result.method == ClassificationMethod.RULE_BASED


@pytest.mark.unit
def test_classify_partial():
    """Test classification of partial understanding responses."""
    test_cases = [
        "somewhat",
        "a little bit",
        "maybe",
        "kind of",
        "sort of",
        "I think so",
        "I guess",
    ]

    for text in test_cases:
        result = classify_text(text, None, "req-3")
        assert result.intent == IntentCategory.PARTIAL, f"Failed for: {text}"
        assert result.method == ClassificationMethod.RULE_BASED


@pytest.mark.unit
def test_classify_question():
    """Test classification of question responses."""
    test_cases = [
        "what do you mean?",
        "can you explain that?",
        "how does that work?",
        "why is that?",
    ]

    for text in test_cases:
        result = classify_text(text, None, "req-4")
        assert result.intent == IntentCategory.QUESTION, f"Failed for: {text}"
        assert result.method == ClassificationMethod.RULE_BASED


@pytest.mark.unit
def test_classify_skip():
    """Test classification of skip responses."""
    test_cases = [
        "just tell me the answer",
        "skip the explanation",
        "give me the answer",
    ]

    for text in test_cases:
        result = classify_text(text, None, "req-5")
        assert result.intent == IntentCategory.SKIP, f"Failed for: {text}"
        assert result.method == ClassificationMethod.RULE_BASED


@pytest.mark.unit
def test_classify_with_context():
    """Test classification with context still resolves correctly."""
    result = classify_text("yes", "Do you understand derivatives?", "req-6")

    assert result.intent == IntentCategory.AFFIRMATIVE


@pytest.mark.unit
def test_classify_response_structure():
    """Test that response has intent, confidence (0-1), and method fields."""
    result = classify_text("yes", None, "req-7")

    assert isinstance(result.intent, IntentCategory)
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.method, ClassificationMethod)


@pytest.mark.unit
def test_classify_matched_patterns():
    """Test that rule-based results include matched_patterns."""
    result = classify_text("yes, I understand", None, "req-8")

    assert result.method == ClassificationMethod.RULE_BASED
    assert result.matched_patterns is not None
    assert len(result.matched_patterns) > 0
