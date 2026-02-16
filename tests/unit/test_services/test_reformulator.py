from unittest.mock import MagicMock, patch

import pytest

from tests.unit.test_services.conftest import _ensure_env, _ensure_path, _mock_logging


@pytest.fixture(scope="module", autouse=True)
def setup_module():
    _ensure_env()
    _ensure_path()
    _mock_logging()


def _make_mock_response(content: str) -> MagicMock:
    """Create a mock OpenAI chat completion response."""
    mock_message = MagicMock()
    mock_message.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


@pytest.mark.unit
@patch("src.services.reformulator.service.Config.REFORMULATION.USE_LLM", False)
def test_reformulate_llm_disabled():
    """Test reformulation when LLM is disabled returns input as-is."""
    from src.services.reformulator.service import reformulate_query

    result = reformulate_query(
        processed_input="what is derivative of x squared",
        input_type="text",
        request_id="test-req-1",
    )

    assert result.reformulated_query == "what is derivative of x squared"
    assert result.original_input == "what is derivative of x squared"
    assert "LLM reformulation disabled" in result.improvements_made[0]


@pytest.mark.unit
@patch("src.services.reformulator.service.Config.REFORMULATION.USE_LLM", True)
@patch("src.services.reformulator.service.reformulator_client")
def test_reformulate_success(mock_client):
    """Test successful reformulation via LLM."""
    from src.services.reformulator.service import reformulate_query

    mock_client.chat.completions.create.return_value = _make_mock_response(
        "What is the derivative of x^2?"
    )

    result = reformulate_query(
        processed_input="what is derivative of x squared",
        input_type="text",
        request_id="test-req-2",
    )

    assert result.reformulated_query == "What is the derivative of x^2?"
    assert result.original_input == "what is derivative of x squared"
    assert len(result.improvements_made) > 0


@pytest.mark.unit
@patch("src.services.reformulator.service.Config.REFORMULATION.USE_LLM", True)
@patch("src.services.reformulator.service.reformulator_client")
def test_reformulate_removes_think_tags(mock_client):
    """Test that reformulation removes <think> tags from DeepSeek-R1 style responses."""
    from src.services.reformulator.service import reformulate_query

    mock_client.chat.completions.create.return_value = _make_mock_response(
        "<think>Let me analyze this...</think>What is the derivative of x^2?"
    )

    result = reformulate_query(
        processed_input="what is derivative of x squared",
        input_type="text",
        request_id="test-req-3",
    )

    assert "<think>" not in result.reformulated_query
    assert "</think>" not in result.reformulated_query
    assert "What is the derivative of x^2?" in result.reformulated_query


@pytest.mark.unit
@patch("src.services.reformulator.service.Config.REFORMULATION.USE_LLM", True)
@patch("src.services.reformulator.service.reformulator_client")
def test_reformulate_removes_quotes(mock_client):
    """Test that reformulation removes surrounding quotes."""
    from src.services.reformulator.service import reformulate_query

    mock_client.chat.completions.create.return_value = _make_mock_response(
        '"What is the derivative of x^2?"'
    )

    result = reformulate_query(
        processed_input="what is derivative of x squared",
        input_type="text",
        request_id="test-req-4",
    )

    assert not result.reformulated_query.startswith('"')
    assert not result.reformulated_query.endswith('"')


@pytest.mark.unit
@patch("src.services.reformulator.service.Config.REFORMULATION.USE_LLM", True)
@patch("src.services.reformulator.service.reformulator_client")
def test_reformulate_empty_response_fallback(mock_client):
    """Test that reformulation falls back to original when LLM returns empty."""
    from src.services.reformulator.service import reformulate_query

    mock_client.chat.completions.create.return_value = _make_mock_response("")

    result = reformulate_query(
        processed_input="test question",
        input_type="text",
        request_id="test-req-5",
    )

    assert result.reformulated_query == "test question"
    assert "none (reformulation failed)" in result.improvements_made


@pytest.mark.unit
@patch("src.services.reformulator.service.Config.REFORMULATION.USE_LLM", True)
@patch("src.services.reformulator.service.reformulator_client")
def test_reformulate_llm_error(mock_client):
    """Test that LLM failure raises HTTPException(503)."""
    from fastapi import HTTPException

    from src.services.reformulator.service import reformulate_query

    mock_client.chat.completions.create.side_effect = Exception("Connection error")

    with pytest.raises(HTTPException) as exc_info:
        reformulate_query(
            processed_input="test question",
            input_type="text",
            request_id="test-req-6",
        )

    assert exc_info.value.status_code == 503


@pytest.mark.unit
@patch("src.services.reformulator.service.Config.REFORMULATION.USE_LLM", True)
@patch("src.services.reformulator.service.reformulator_client")
def test_reformulate_special_characters(mock_client):
    """Test that unicode and special characters are preserved."""
    from src.services.reformulator.service import reformulate_query

    mock_client.chat.completions.create.return_value = _make_mock_response(
        "What is \u222b x\u00b2 dx?"
    )

    result = reformulate_query(
        processed_input="integral of x squared",
        input_type="text",
        request_id="test-req-7",
    )

    assert "\u222b" in result.reformulated_query
    assert "\u00b2" in result.reformulated_query


@pytest.mark.unit
@patch("src.services.reformulator.service.Config.REFORMULATION.USE_LLM", True)
@patch("src.services.reformulator.service.reformulator_client")
def test_reformulate_detects_improvements(mock_client):
    """Test that notation standardization and capitalization improvements are detected."""
    from src.services.reformulator.service import reformulate_query

    mock_client.chat.completions.create.return_value = _make_mock_response(
        "What is the derivative of x^2?"
    )

    result = reformulate_query(
        processed_input="what is derivative of x squared",
        input_type="text",
        request_id="test-req-8",
    )

    improvements = result.improvements_made
    assert any("notation" in imp.lower() for imp in improvements)
    assert any("capitalization" in imp.lower() for imp in improvements)
