import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        SMALL_LLM_URL = os.getenv("SMALL_LLM_SERVICE_URL", "http://small-llm:8005")

    class REFORMULATION:
        # Whether to use the LLM for reformulation or just return the input
        USE_LLM = os.getenv("USE_LLM_FOR_REFORMULATION", "true").lower() == "true"
        # Maximum conversation history messages to include in context
        MAX_CONTEXT_MESSAGES = int(os.getenv("REFORMULATOR_MAX_CONTEXT", "5"))
        # Maximum length of summarized context
        MAX_CONTEXT_LENGTH = int(os.getenv("REFORMULATOR_MAX_CONTEXT_LENGTH", "500"))
