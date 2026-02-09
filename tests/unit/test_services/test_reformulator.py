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
@patch("src.main.client")
def test_reformulate_success(mock_openai_client):
    """Test successful reformulation via LLM"""
    # Mock OpenAI client response
    mock_message = MagicMock()
    mock_message.content = "What is the derivative of x^2?"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_response

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
@patch("src.main.client")
def test_reformulate_llm_error(mock_openai_client):
    """Test reformulation when LLM service returns error"""
    mock_openai_client.chat.completions.create.side_effect = Exception(
        "Connection error"
    )

    request_data = {
        "processed_input": "test question",
        "input_type": "text",
    }

    response = client.post("/reformulate", json=request_data)

    assert response.status_code == 503
    assert "error" in response.json()["detail"].lower()


@pytest.mark.unit
@patch("src.main.Config.REFORMULATION.USE_LLM", True)
@patch("src.main.client")
def test_reformulate_removes_think_tags(mock_openai_client):
    """Test that reformulation removes <think> tags from DeepSeek-R1 style responses"""
    mock_message = MagicMock()
    mock_message.content = (
        "<think>Let me analyze this...</think>What is the derivative of x^2?"
    )
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_response

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
@patch("src.main.client")
def test_reformulate_removes_quotes(mock_openai_client):
    """Test that reformulation removes surrounding quotes"""
    mock_message = MagicMock()
    mock_message.content = '"What is the derivative of x^2?"'
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_response

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
@patch("src.main.client")
def test_reformulate_empty_response_fallback(mock_openai_client):
    """Test that reformulation falls back to original when LLM returns empty"""
    mock_message = MagicMock()
    mock_message.content = ""
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_response

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
@patch("src.main.client")
def test_reformulate_special_characters(mock_openai_client):
    """Test reformulation with special characters and unicode"""
    mock_message = MagicMock()
    mock_message.content = "What is ∫ x² dx?"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_response

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
@patch("src.main.client")
def test_reformulate_detects_improvements(mock_openai_client):
    """Test that reformulation detects specific improvements made"""
    mock_message = MagicMock()
    mock_message.content = "What is the derivative of x^2?"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_response

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
