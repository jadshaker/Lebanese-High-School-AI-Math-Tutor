import pytest


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
    Mock all external API calls (OpenAI and Ollama) for integration/E2E tests.

    IMPORTANT: This fixture is for tests that run WITHOUT Docker. Integration and E2E tests
    that call Docker services will still need real APIs because `responses` mocks only work
    in the same Python process.

    By default, tests use mocked APIs (fast, no external dependencies).
    Use --use-real-apis flag to test against real APIs.

    Usage in tests:
        @pytest.mark.integration
        def test_something(mock_external_apis):
            # Test will use mocked APIs by default (requires Docker services running)
            pass

    Note: For true mocking without Docker, tests should use TestClient instead of HTTP calls.
    """
    use_real_apis = request.config.getoption("--use-real-apis")

    if use_real_apis:
        # Skip mocking - use real APIs
        yield None
        return

    # Note: These mocks only work for HTTP calls made from the test process itself.
    # They do NOT work for calls made by Docker services.
    # Integration tests that call Gateway in Docker will still need real APIs.
    yield None
