import time

import pytest
import responses


def pytest_addoption(parser):
    """Add custom pytest command-line options"""
    parser.addoption(
        "--use-real-apis",
        action="store_true",
        default=False,
        help="Use real APIs instead of mocks for integration/E2E tests (requires OpenAI keys + HPC connection)",
    )


@pytest.fixture
def sample_question():
    """Sample math question for testing"""
    return "What is the derivative of x^2?"


@pytest.fixture
def sample_embedding():
    """Mock 1536-dimensional embedding vector"""
    return [0.1] * 1536


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response"""
    return {"choices": [{"message": {"content": "The derivative is 2x"}}]}


@pytest.fixture
def sample_query_request():
    """Sample query request payload"""
    return {"query": "What is the derivative of x^2?"}


@pytest.fixture
def sample_embedding_request():
    """Sample embedding request payload"""
    return {"text": "What is the derivative of x^2?"}


@pytest.fixture
def sample_cached_answer():
    """Sample cached answer from cache service"""
    return {
        "answer": "The derivative of x^2 is 2x",
        "similarity": 0.95,
        "source": "cache",
    }


@pytest.fixture(scope="function")
def mock_external_apis(request):
    """
    Mock all external API calls (OpenAI and Ollama services).

    By default, tests use mocked APIs (fast, no external dependencies).
    Use --use-real-apis flag to test against real APIs locally.

    Usage:
        # Mocked APIs (default)
        pytest tests/integration -v

        # Real APIs (requires OpenAI keys + HPC)
        pytest tests/integration -v --use-real-apis

    In test:
        @pytest.mark.integration
        def test_something(mock_external_apis):
            # Test will use mocked APIs by default
            pass
    """
    use_real_apis = request.config.getoption("--use-real-apis")

    if use_real_apis:
        # Skip mocking - use real APIs
        yield None
        return

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        # Mock OpenAI Embedding API (text-embedding-3-small)
        rsps.add(
            responses.POST,
            "http://localhost:8002/embed",
            json={
                "embedding": [0.1] * 1536,
                "model": "text-embedding-3-small",
                "dimensions": 1536,
            },
            status=200,
        )

        # Mock OpenAI Large LLM (GPT-4o-mini)
        rsps.add(
            responses.POST,
            "http://localhost:8001/v1/chat/completions",
            json={
                "id": "chatcmpl-mock-large-llm",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "The derivative of x^2 is 2x. This follows from the power rule: d/dx(x^n) = n*x^(n-1).",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
            status=200,
        )

        # Mock Ollama Small LLM (DeepSeek-R1:7b)
        rsps.add(
            responses.POST,
            "http://localhost:8005/v1/chat/completions",
            json={
                "id": "chatcmpl-mock-small-llm",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "deepseek-r1:7b",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "To find the derivative of x^2, use the power rule. The answer is 2x.",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
            status=200,
        )

        # Mock Ollama Reformulator
        rsps.add(
            responses.POST,
            "http://localhost:8007/reformulate",
            json={
                "reformulated_query": "Calculate the derivative of the function f(x) = x^2 with respect to x",
                "original_input": "what is 2+2",
                "improvements_made": [
                    "Added mathematical notation",
                    "Clarified the question structure",
                    "Made query more precise",
                ],
            },
            status=200,
        )

        # Mock Ollama Fine-Tuned Model (TinyLlama)
        rsps.add(
            responses.POST,
            "http://localhost:8006/v1/chat/completions",
            json={
                "id": "chatcmpl-mock-fine-tuned",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "tinyllama:latest",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "The derivative is 2x.",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
            status=200,
        )

        # Mock Input Processor
        rsps.add(
            responses.POST,
            "http://localhost:8004/process",
            json={
                "processed_input": "what is 2+2",
                "input_type": "text",
            },
            status=200,
        )

        # Mock Cache Search
        rsps.add(
            responses.POST,
            "http://localhost:8003/search",
            json={
                "results": [
                    {
                        "question": "What is the derivative of x squared?",
                        "answer": "The derivative is 2x",
                        "similarity_score": 0.85,
                    }
                ]
            },
            status=200,
        )

        # Mock Cache Save
        rsps.add(
            responses.POST,
            "http://localhost:8003/save",
            json={"status": "success", "message": "Answer cached successfully"},
            status=200,
        )

        yield rsps
