import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        REFORMULATOR_LLM_URL = os.getenv(
            "REFORMULATOR_LLM_SERVICE_URL", "http://small-llm:8005"
        )

    REFORMULATOR_LLM_MODEL_NAME = os.environ["REFORMULATOR_LLM_MODEL_NAME"]
    REFORMULATOR_LLM_API_KEY = os.environ["REFORMULATOR_LLM_API_KEY"]
    REFORMULATOR_LLM_TEMPERATURE = float(
        os.getenv("REFORMULATOR_LLM_TEMPERATURE", "0.6")
    )
    REFORMULATOR_LLM_TOP_P = float(os.getenv("REFORMULATOR_LLM_TOP_P", "0.9"))
    _reformulator_max_tokens = os.getenv("REFORMULATOR_LLM_MAX_TOKENS")
    REFORMULATOR_LLM_MAX_TOKENS: int | None = (
        int(_reformulator_max_tokens) if _reformulator_max_tokens else None
    )
    REFORMULATOR_LLM_TIMEOUT = float(os.getenv("REFORMULATOR_LLM_TIMEOUT", "300"))

    class REFORMULATION:
        # Whether to use the LLM for reformulation or just return the input
        USE_LLM = os.getenv("REFORMULATOR_USE_LLM", "true").lower() == "true"
        # Maximum conversation history messages to include in context
        MAX_CONTEXT_MESSAGES = int(os.getenv("REFORMULATOR_MAX_CONTEXT", "5"))
        # Maximum length of summarized context
        MAX_CONTEXT_LENGTH = int(os.getenv("REFORMULATOR_MAX_CONTEXT_LENGTH", "500"))
