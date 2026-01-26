import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# Module-level setup - load app and create client
@pytest.fixture(scope="module", autouse=True)
def setup_module(reformulator_app):
    """Set up module-level client for reformulator service"""
    global client
    client = TestClient(reformulator_app)


@pytest.mark.unit
@patch("src.main.urlopen")
def test_health_endpoint_healthy(mock_urlopen):
    """Test health check when Small LLM service is reachable"""
    # Mock Small LLM /health response
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"status": "healthy"}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "reformulator"
    assert data["small_llm_service"] == "reachable"


@pytest.mark.unit
@patch("src.main.urlopen")
def test_health_endpoint_degraded(mock_urlopen):
    """Test health check when Small LLM service is unreachable"""
    mock_urlopen.side_effect = Exception("Connection refused")

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["small_llm_service"] == "unreachable"


@pytest.mark.unit
@patch("src.main.Config.REFORMULATION.USE_LLM", False)
def test_reformulate_llm_disabled():
    """Test reformulation when LLM is disabled (returns input as-is)"""
    request_data = {
        "processed_input": "what is derivative of x squared",
        "input_type": "text",
    }

    response = client.post("/reformulate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["reformulated_query"] == "what is derivative of x squared"
    assert data["original_input"] == "what is derivative of x squared"
    assert "LLM reformulation disabled" in data["improvements_made"][0]


@pytest.mark.unit
@patch("src.main.Config.REFORMULATION.USE_LLM", True)
@patch("src.main.urlopen")
def test_reformulate_success(mock_urlopen):
    """Test successful reformulation via LLM"""
    # Mock Small LLM response
    llm_response = {
        "choices": [{"message": {"content": "What is the derivative of x^2?"}}]
    }
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(llm_response).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    request_data = {
        "processed_input": "what is derivative of x squared",
        "input_type": "text",
    }

    response = client.post("/reformulate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["reformulated_query"] == "What is the derivative of x^2?"
    assert data["original_input"] == "what is derivative of x squared"
    assert len(data["improvements_made"]) > 0


@pytest.mark.unit
def test_reformulate_missing_fields():
    """Test reformulation with missing required fields"""
    response = client.post("/reformulate", json={"processed_input": "test"})
    assert response.status_code == 422  # Validation error


@pytest.mark.unit
@patch("src.main.Config.REFORMULATION.USE_LLM", True)
@patch("src.main.urlopen")
def test_reformulate_llm_error(mock_urlopen):
    """Test reformulation when LLM service returns error"""
    mock_urlopen.side_effect = Exception("Connection error")

    request_data = {
        "processed_input": "test question",
        "input_type": "text",
    }

    response = client.post("/reformulate", json=request_data)

    assert response.status_code == 503
    assert "error" in response.json()["detail"].lower()


@pytest.mark.unit
@patch("src.main.Config.REFORMULATION.USE_LLM", True)
@patch("src.main.urlopen")
def test_reformulate_removes_think_tags(mock_urlopen):
    """Test that reformulation removes <think> tags from DeepSeek-R1 style responses"""
    # Mock Small LLM response with <think> tags
    llm_response = {
        "choices": [
            {
                "message": {
                    "content": "<think>Let me analyze this...</think>What is the derivative of x^2?"
                }
            }
        ]
    }
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(llm_response).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    request_data = {
        "processed_input": "what is derivative of x squared",
        "input_type": "text",
    }

    response = client.post("/reformulate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "<think>" not in data["reformulated_query"]
    assert "</think>" not in data["reformulated_query"]
    assert "What is the derivative of x^2?" in data["reformulated_query"]


@pytest.mark.unit
@patch("src.main.Config.REFORMULATION.USE_LLM", True)
@patch("src.main.urlopen")
def test_reformulate_removes_quotes(mock_urlopen):
    """Test that reformulation removes surrounding quotes"""
    # Mock Small LLM response with quotes
    llm_response = {
        "choices": [{"message": {"content": '"What is the derivative of x^2?"'}}]
    }
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(llm_response).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    request_data = {
        "processed_input": "what is derivative of x squared",
        "input_type": "text",
    }

    response = client.post("/reformulate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert not data["reformulated_query"].startswith('"')
    assert not data["reformulated_query"].endswith('"')


@pytest.mark.unit
@patch("src.main.Config.REFORMULATION.USE_LLM", True)
@patch("src.main.urlopen")
def test_reformulate_empty_response_fallback(mock_urlopen):
    """Test that reformulation falls back to original when LLM returns empty"""
    # Mock Small LLM response with empty content
    llm_response = {"choices": [{"message": {"content": ""}}]}
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(llm_response).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    request_data = {
        "processed_input": "test question",
        "input_type": "text",
    }

    response = client.post("/reformulate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["reformulated_query"] == "test question"
    assert "none (reformulation failed)" in data["improvements_made"]


@pytest.mark.unit
@patch("src.main.Config.REFORMULATION.USE_LLM", True)
@patch("src.main.urlopen")
def test_reformulate_special_characters(mock_urlopen):
    """Test reformulation with special characters and unicode"""
    # Mock Small LLM response
    llm_response = {"choices": [{"message": {"content": "What is ∫ x² dx?"}}]}
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(llm_response).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    request_data = {
        "processed_input": "integral of x squared",
        "input_type": "text",
    }

    response = client.post("/reformulate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "∫" in data["reformulated_query"]
    assert "²" in data["reformulated_query"]


@pytest.mark.unit
@patch("src.main.Config.REFORMULATION.USE_LLM", True)
@patch("src.main.urlopen")
def test_reformulate_detects_improvements(mock_urlopen):
    """Test that reformulation detects specific improvements made"""
    # Mock Small LLM response with multiple improvements
    llm_response = {
        "choices": [{"message": {"content": "What is the derivative of x^2?"}}]
    }
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(llm_response).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    request_data = {
        "processed_input": "what is derivative of x squared",
        "input_type": "text",
    }

    response = client.post("/reformulate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    improvements = data["improvements_made"]
    # Should detect notation standardization (x^2) and capitalization
    assert any("notation" in imp.lower() for imp in improvements)
    assert any("capitalization" in imp.lower() for imp in improvements)
