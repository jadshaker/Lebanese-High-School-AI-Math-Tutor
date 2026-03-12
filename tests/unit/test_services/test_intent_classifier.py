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
def test_classify_correction():
    """Test classification of correction responses via rule-based matching."""
    test_cases = [
        "no it is 2x^5 + 4x^-3",
        "no, the question is about integrals",
        "I meant the derivative of sin(x)",
        "actually it is 3x^2 + 1",
        "sorry, my question was about limits",
        "wait, the equation is y = 2x + 3",
        "that's not what I asked",
        "I made a mistake",
        "no, I mean the integral of x^3",
    ]

    for text in test_cases:
        result = classify_text(text, None, "req-correction")
        assert result.intent == IntentCategory.CORRECTION, f"Failed for: {text}"


@pytest.mark.unit
def test_bare_no_is_negative():
    """Test that a bare 'no' (without correction content) is still NEGATIVE."""
    test_cases = [
        "no",
        "No.",
        "no!",
    ]

    for text in test_cases:
        result = classify_text(text, None, "req-bare-no")
        assert result.intent == IntentCategory.NEGATIVE, f"Failed for: {text}"


@pytest.mark.unit
def test_correction_beats_negative():
    """Test that CORRECTION takes priority when both could match."""
    result = classify_text("no it is 2x^5 + 4x^-3", None, "req-priority")
    assert result.intent == IntentCategory.CORRECTION


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
def test_classify_answer_attempt():
    """Test classification of answer attempt responses via rule-based matching."""
    test_cases = [
        "i think it is 1/x power 4",
        "I think it's x^2",
        "is it 1/x^2",
        "the answer is 5",
        "it equals 3x + 1",
        "you subtract the exponents",
        "we get x^-2",
        "it is 1/x",
        "I think we use the power rule",
        "I think the answer is -1/x",
    ]

    for text in test_cases:
        result = classify_text(text, None, "req-answer")
        assert (
            result.intent == IntentCategory.ANSWER_ATTEMPT
        ), f"Failed for: {text} (got {result.intent.value})"


@pytest.mark.unit
def test_answer_attempt_not_confused_with_partial():
    """Test that 'I think it is X' is ANSWER_ATTEMPT, not PARTIAL ('I think so')."""
    result = classify_text("I think it is 3x^2", None, "req-not-partial")
    assert result.intent == IntentCategory.ANSWER_ATTEMPT

    # But "I think so" should still be PARTIAL
    result = classify_text("I think so", None, "req-partial")
    assert result.intent == IntentCategory.PARTIAL


@pytest.mark.unit
def test_classify_matched_patterns():
    """Test that rule-based results include matched_patterns."""
    result = classify_text("yes, I understand", None, "req-8")

    assert result.method == ClassificationMethod.RULE_BASED
    assert result.matched_patterns is not None
    assert len(result.matched_patterns) > 0
