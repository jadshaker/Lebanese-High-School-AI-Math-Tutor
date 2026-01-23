import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        SMALL_LLM_URL = os.getenv("SMALL_LLM_SERVICE_URL", "http://small-llm:8005")

    class REFORMULATION:
        # Whether to use the LLM for reformulation or just return the input
        USE_LLM = os.getenv("USE_LLM_FOR_REFORMULATION", "true").lower() == "true"
