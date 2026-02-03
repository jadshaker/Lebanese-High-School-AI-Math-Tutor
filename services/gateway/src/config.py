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
        VECTOR_CACHE_URL = os.getenv(
            "VECTOR_CACHE_SERVICE_URL", "http://vector-cache:8003"
        )
        SMALL_LLM_URL = os.getenv("SMALL_LLM_SERVICE_URL", "http://small-llm:8005")
        LARGE_LLM_URL = os.getenv("LARGE_LLM_SERVICE_URL", "http://large-llm:8001")
        FINE_TUNED_MODEL_URL = os.getenv(
            "FINE_TUNED_MODEL_SERVICE_URL", "http://fine-tuned-model:8006"
        )
        SESSION_URL = os.getenv("SESSION_SERVICE_URL", "http://session:8010")
        INTENT_CLASSIFIER_URL = os.getenv(
            "INTENT_CLASSIFIER_SERVICE_URL", "http://intent-classifier:8009"
        )

    # Vector cache configuration
    CACHE_TOP_K = int(os.getenv("CACHE_TOP_K", "5"))

    # 5-tier confidence routing thresholds
    class CONFIDENCE_TIERS:
        TIER_1_THRESHOLD = float(os.getenv("CONFIDENCE_TIER_1", "0.95"))  # Direct cache
        TIER_2_THRESHOLD = float(os.getenv("CONFIDENCE_TIER_2", "0.85"))  # Small LLM validate
        TIER_3_THRESHOLD = float(os.getenv("CONFIDENCE_TIER_3", "0.70"))  # Small LLM with context
        TIER_4_THRESHOLD = float(os.getenv("CONFIDENCE_TIER_4", "0.50"))  # Fine-tuned first
        # Below TIER_4 → Large LLM directly

    # Tutoring configuration
    class TUTORING:
        MAX_INTERACTION_DEPTH = int(os.getenv("TUTORING_MAX_DEPTH", "5"))
        ENABLE_TUTORING_MODE = (
            os.getenv("TUTORING_ENABLE", "true").lower() == "true"
        )
