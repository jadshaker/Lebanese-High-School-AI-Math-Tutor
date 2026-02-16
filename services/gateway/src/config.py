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

    class MODELS:
        SMALL_LLM_MODEL_NAME = os.environ["SMALL_LLM_MODEL_NAME"]
        SMALL_LLM_TEMPERATURE = float(os.getenv("SMALL_LLM_TEMPERATURE", "0.7"))
        SMALL_LLM_TOP_P = float(os.getenv("SMALL_LLM_TOP_P", "0.9"))
        _small_llm_max_tokens = os.getenv("SMALL_LLM_MAX_TOKENS")
        SMALL_LLM_MAX_TOKENS: int | None = (
            int(_small_llm_max_tokens) if _small_llm_max_tokens else None
        )
        SMALL_LLM_TIMEOUT = int(os.getenv("SMALL_LLM_TIMEOUT", "300"))

        FINE_TUNED_MODEL_NAME = os.environ["FINE_TUNED_MODEL_NAME"]
        FINE_TUNED_MODEL_TEMPERATURE = float(
            os.getenv("FINE_TUNED_MODEL_TEMPERATURE", "0.7")
        )
        FINE_TUNED_MODEL_TOP_P = float(os.getenv("FINE_TUNED_MODEL_TOP_P", "0.9"))
        _fine_tuned_max_tokens = os.getenv("FINE_TUNED_MODEL_MAX_TOKENS")
        FINE_TUNED_MODEL_MAX_TOKENS: int | None = (
            int(_fine_tuned_max_tokens) if _fine_tuned_max_tokens else None
        )
        FINE_TUNED_MODEL_TIMEOUT = int(os.getenv("FINE_TUNED_MODEL_TIMEOUT", "300"))

        LARGE_LLM_MODEL_NAME = os.environ["LARGE_LLM_MODEL_NAME"]
        LARGE_LLM_TEMPERATURE = float(os.getenv("LARGE_LLM_TEMPERATURE", "0.7"))
        LARGE_LLM_TOP_P = float(os.getenv("LARGE_LLM_TOP_P", "0.9"))
        _large_llm_max_tokens = os.getenv("LARGE_LLM_MAX_TOKENS")
        LARGE_LLM_MAX_TOKENS: int | None = (
            int(_large_llm_max_tokens) if _large_llm_max_tokens else None
        )
        LARGE_LLM_TIMEOUT = int(os.getenv("LARGE_LLM_TIMEOUT", "300"))

    # Vector cache configuration
    CACHE_TOP_K = int(os.getenv("CACHE_TOP_K", "5"))

    # 4-tier confidence routing thresholds
    class CONFIDENCE_TIERS:
        TIER_1_THRESHOLD = float(
            os.getenv("CONFIDENCE_TIER_1", "0.85")
        )  # Small LLM validate-or-generate
        TIER_2_THRESHOLD = float(
            os.getenv("CONFIDENCE_TIER_2", "0.70")
        )  # Small LLM with context
        TIER_3_THRESHOLD = float(
            os.getenv("CONFIDENCE_TIER_3", "0.50")
        )  # Fine-tuned model
        # Below TIER_3 → Large LLM directly

    # Tutoring configuration
    class TUTORING:
        MAX_INTERACTION_DEPTH = int(os.getenv("TUTORING_MAX_DEPTH", "5"))
        ENABLE_TUTORING_MODE = os.getenv("TUTORING_ENABLED", "true").lower() == "true"
        CACHE_THRESHOLD = float(os.getenv("TUTORING_INTERACTION_THRESHOLD", "0.85"))
