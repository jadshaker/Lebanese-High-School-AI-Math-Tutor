def test_pytest_working():
    """Smoke test to verify pytest is properly configured"""
    assert True


def test_fixtures_available(sample_question, sample_embedding, mock_openai_response):
    """Test that common fixtures are available"""
    assert sample_question == "What is the derivative of x^2?"
    assert len(sample_embedding) == 1536
    assert "choices" in mock_openai_response
    assert (
        mock_openai_response["choices"][0]["message"]["content"]
        == "The derivative is 2x"
    )
