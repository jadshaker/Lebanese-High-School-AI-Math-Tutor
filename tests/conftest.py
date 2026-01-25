import pytest


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
