import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        GATEWAY_URL = os.getenv("GATEWAY_SERVICE_URL", "http://gateway:8000")
        INPUT_PROCESSOR_URL = os.getenv(
            "INPUT_PROCESSOR_SERVICE_URL", "http://input-processor:8004"
        )
        REFORMULATOR_URL = os.getenv(
            "REFORMULATOR_SERVICE_URL", "http://reformulator:8007"
        )
        EMBEDDING_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:8002")
        CACHE_URL = os.getenv("CACHE_SERVICE_URL", "http://cache:8003")
        SMALL_LLM_URL = os.getenv("SMALL_LLM_SERVICE_URL", "http://small-llm:8005")
        LARGE_LLM_URL = os.getenv("LARGE_LLM_SERVICE_URL", "http://large-llm:8001")
        FINE_TUNED_MODEL_URL = os.getenv(
            "FINE_TUNED_MODEL_SERVICE_URL", "http://fine-tuned-model:8006"
        )

    # Cache configuration
    CACHE_TOP_K = int(os.getenv("CACHE_TOP_K", "5"))
