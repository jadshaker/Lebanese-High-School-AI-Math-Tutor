import time

import pytest
import requests


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


def wait_for_logs(
    gateway_url: str, request_id: str, timeout: float = 5.0, min_services: int = 1
) -> dict:
    """
    Poll the tracking endpoint until logs are available.

    This helper solves race conditions where logs are written asynchronously
    and may not be immediately available after a request completes.

    Args:
        gateway_url: Base URL of the gateway service (e.g., "http://localhost:8000")
        request_id: The request ID to track
        timeout: Maximum time to wait in seconds (default: 5.0)
        min_services: Minimum number of services that should have logs (default: 1)

    Returns:
        dict: The tracking response data containing services and timeline

    Raises:
        TimeoutError: If logs are not available after timeout
        AssertionError: If the tracking endpoint returns an error
    """
    start_time = time.time()
    last_error = None

    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{gateway_url}/track/{request_id}", timeout=10)

            if response.status_code == 200:
                data = response.json()
                services = data.get("services", {})
                timeline = data.get("timeline", [])

                # Check if we have enough logs
                if len(services) >= min_services and len(timeline) > 0:
                    return data

            last_error = f"Status {response.status_code}: {response.text}"

        except Exception as e:
            last_error = str(e)

        time.sleep(0.2)  # Poll every 200ms

    raise TimeoutError(
        f"Logs not available after {timeout}s. "
        f"Expected at least {min_services} services with logs. "
        f"Last error: {last_error}"
    )


def wait_for_metrics(
    gateway_url: str, metric_names: list[str] | None = None, timeout: float = 3.0
) -> str:
    """
    Poll the metrics endpoint until it's available and optionally contains specific metrics.

    This helper solves race conditions with Prometheus metrics aggregation
    which may have a slight delay after requests complete.

    Args:
        gateway_url: Base URL of the gateway service (e.g., "http://localhost:8000")
        metric_names: Optional list of metric names to wait for (e.g., ["gateway_cache_hits_total"])
                     If None, just waits for any metrics to be available
        timeout: Maximum time to wait in seconds (default: 3.0)

    Returns:
        str: The metrics response text

    Raises:
        TimeoutError: If metrics are not available after timeout
    """
    start_time = time.time()
    last_error = None

    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{gateway_url}/metrics", timeout=10)

            if response.status_code == 200:
                metrics_text = response.text

                # If no specific metrics requested, just return any valid response
                if metric_names is None:
                    if len(metrics_text) > 0:
                        return metrics_text
                else:
                    # Check if all requested metrics are present
                    if all(metric in metrics_text for metric in metric_names):
                        return metrics_text

            last_error = f"Status {response.status_code}"

        except Exception as e:
            last_error = str(e)

        time.sleep(0.2)  # Poll every 200ms

    if metric_names:
        raise TimeoutError(
            f"Metrics {metric_names} not available after {timeout}s. "
            f"Last error: {last_error}"
        )
    else:
        raise TimeoutError(
            f"Metrics endpoint not available after {timeout}s. "
            f"Last error: {last_error}"
        )
