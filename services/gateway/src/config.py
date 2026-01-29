import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        LARGE_LLM_URL = os.getenv("LARGE_LLM_SERVICE_URL", "http://large-llm:8001")
        SMALL_LLM_URL = os.getenv("SMALL_LLM_SERVICE_URL", "http://small-llm:8005")
        EMBEDDING_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:8002")
        REFORMULATOR_URL = os.getenv(
            "REFORMULATOR_SERVICE_URL", "http://reformulator:8009"
        )
        VECTOR_CACHE_URL = os.getenv(
            "VECTOR_CACHE_SERVICE_URL", "http://vector-cache:8003"
        )
        SESSION_URL = os.getenv("SESSION_SERVICE_URL", "http://session:8010")
        INTENT_CLASSIFIER_URL = os.getenv(
            "INTENT_CLASSIFIER_SERVICE_URL", "http://intent-classifier:8011"
        )

    class CONFIDENCE:
        # Tier thresholds for confidence routing
        TIER_1_THRESHOLD = 0.90  # Direct return from cache
        TIER_2_THRESHOLD = 0.70  # Small LLM validates
        TIER_3_THRESHOLD = 0.50  # Small LLM with context
        # Below TIER_3 = generate with API LLM

    class TUTORING:
        MAX_DEPTH = 4
        ENABLE_TUTORING = True
