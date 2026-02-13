from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# Module-level setup - load app and create client
@pytest.fixture(scope="module", autouse=True)
def setup_module(intent_classifier_app):
    """Set up module-level client for intent classifier service"""
    global client
    client = TestClient(intent_classifier_app)


@pytest.mark.unit
def test_health_endpoint():
    """Test health check endpoint returns correct structure"""
    with patch("src.main.urlopen") as mock_urlopen:
        # Mock Small LLM health check failure (expected in unit tests)
        mock_urlopen.side_effect = Exception("Service unavailable")

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert data["service"] == "intent_classifier"
        assert "small_llm_available" in data


@pytest.mark.unit
def test_classify_affirmative():
    """Test classification of affirmative responses"""
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
        response = client.post("/classify", json={"text": text})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "affirmative", f"Failed for: {text}"
        assert data["method"] == "rule_based"
        assert data["confidence"] >= 0.8


@pytest.mark.unit
def test_classify_negative():
    """Test classification of negative responses"""
    test_cases = [
        "no",
        "I don't know",
        "I don't understand",
        "I'm confused",
        "not at all",
    ]

    for text in test_cases:
        response = client.post("/classify", json={"text": text})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "negative", f"Failed for: {text}"
        assert data["method"] == "rule_based"


@pytest.mark.unit
def test_classify_partial():
    """Test classification of partial understanding responses"""
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
        response = client.post("/classify", json={"text": text})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "partial", f"Failed for: {text}"
        assert data["method"] == "rule_based"


@pytest.mark.unit
def test_classify_question():
    """Test classification of question responses"""
    test_cases = [
        "what do you mean?",
        "can you explain that?",
        "how does that work?",
        "why is that?",
    ]

    for text in test_cases:
        response = client.post("/classify", json={"text": text})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "question", f"Failed for: {text}"
        assert data["method"] == "rule_based"


@pytest.mark.unit
def test_classify_skip():
    """Test classification of skip responses"""
    test_cases = [
        "just tell me the answer",
        "skip the explanation",
        "give me the answer",
    ]

    for text in test_cases:
        response = client.post("/classify", json={"text": text})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "skip", f"Failed for: {text}"
        assert data["method"] == "rule_based"


@pytest.mark.unit
def test_classify_with_context():
    """Test classification with context provided"""
    response = client.post(
        "/classify",
        json={
            "text": "yes",
            "context": "Do you understand derivatives?",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "affirmative"


@pytest.mark.unit
def test_classify_empty_text():
    """Test classification with empty text"""
    response = client.post("/classify", json={"text": ""})
    # Empty text should still work but may fall through to LLM
    assert response.status_code in [200, 422]


@pytest.mark.unit
def test_classify_missing_text():
    """Test classification with missing text field"""
    response = client.post("/classify", json={})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_classify_response_structure():
    """Test that response has correct structure"""
    response = client.post("/classify", json={"text": "yes"})
    assert response.status_code == 200
    data = response.json()

    assert "intent" in data
    assert "confidence" in data
    assert "method" in data
    assert 0.0 <= data["confidence"] <= 1.0
    assert data["method"] in ["rule_based", "llm_based", "hybrid"]


@pytest.mark.unit
def test_classify_matched_patterns():
    """Test that matched patterns are returned for rule-based classification"""
    response = client.post("/classify", json={"text": "yes, I understand"})
    assert response.status_code == 200
    data = response.json()

    if data["method"] == "rule_based":
        assert "matched_patterns" in data
        assert data["matched_patterns"] is not None


@pytest.mark.unit
def test_batch_classify():
    """Test batch classification endpoint"""
    response = client.post(
        "/classify/batch",
        json={
            "texts": ["yes", "no", "maybe"],
            "context": "Test context",
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert "results" in data
    assert len(data["results"]) == 3
    assert data["results"][0]["intent"] == "affirmative"
    assert data["results"][1]["intent"] == "negative"
    assert data["results"][2]["intent"] == "partial"


@pytest.mark.unit
def test_batch_classify_empty_list():
    """Test batch classification with empty list"""
    response = client.post("/classify/batch", json={"texts": []})
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []
