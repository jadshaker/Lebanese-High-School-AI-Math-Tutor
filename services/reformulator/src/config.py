import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        REFORMULATOR_LLM_URL = os.getenv(
            "REFORMULATOR_LLM_SERVICE_URL", "http://small-llm:8005"
        )

    REFORMULATOR_LLM_MODEL_NAME = os.environ["REFORMULATOR_LLM_MODEL_NAME"]
    REFORMULATOR_LLM_API_KEY = os.getenv("REFORMULATOR_LLM_API_KEY", "dummy")

    class REFORMULATION:
        # Whether to use the LLM for reformulation or just return the input
        USE_LLM = os.getenv("USE_LLM_FOR_REFORMULATION", "true").lower() == "true"
