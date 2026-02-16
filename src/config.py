import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class API_KEYS:
        OPENAI = os.getenv("OPENAI_API_KEY")

    # === LLM Backends ===

    class SMALL_LLM:
        SERVICE_URL = os.environ["SMALL_LLM_SERVICE_URL"]
        MODEL_NAME = os.environ["SMALL_LLM_MODEL_NAME"]
        API_KEY = os.environ["SMALL_LLM_API_KEY"]
        TEMPERATURE = float(os.getenv("SMALL_LLM_TEMPERATURE", "0.7"))
        TOP_P = float(os.getenv("SMALL_LLM_TOP_P", "0.9"))
        _max_tokens = os.getenv("SMALL_LLM_MAX_TOKENS")
        MAX_TOKENS: int | None = int(_max_tokens) if _max_tokens else None
        TIMEOUT = float(os.getenv("SMALL_LLM_TIMEOUT", "300"))

    class FINE_TUNED_MODEL:
        SERVICE_URL = os.environ["FINE_TUNED_MODEL_SERVICE_URL"]
        MODEL_NAME = os.environ["FINE_TUNED_MODEL_NAME"]
        API_KEY = os.environ["FINE_TUNED_MODEL_API_KEY"]
        TEMPERATURE = float(os.getenv("FINE_TUNED_MODEL_TEMPERATURE", "0.7"))
        TOP_P = float(os.getenv("FINE_TUNED_MODEL_TOP_P", "0.9"))
        _max_tokens = os.getenv("FINE_TUNED_MODEL_MAX_TOKENS")
        MAX_TOKENS: int | None = int(_max_tokens) if _max_tokens else None
        TIMEOUT = float(os.getenv("FINE_TUNED_MODEL_TIMEOUT", "300"))

    class LARGE_LLM:
        MODEL_NAME = os.environ["LARGE_LLM_MODEL_NAME"]
        TEMPERATURE = float(os.getenv("LARGE_LLM_TEMPERATURE", "0.7"))
        TOP_P = float(os.getenv("LARGE_LLM_TOP_P", "0.9"))
        _max_tokens = os.getenv("LARGE_LLM_MAX_TOKENS")
        MAX_TOKENS: int | None = int(_max_tokens) if _max_tokens else None
        TIMEOUT = float(os.getenv("LARGE_LLM_TIMEOUT", "300"))

    class REFORMULATOR_LLM:
        SERVICE_URL = os.environ["REFORMULATOR_LLM_SERVICE_URL"]
        MODEL_NAME = os.environ["REFORMULATOR_LLM_MODEL_NAME"]
        API_KEY = os.environ["REFORMULATOR_LLM_API_KEY"]
        TEMPERATURE = float(os.getenv("REFORMULATOR_LLM_TEMPERATURE", "0.6"))
        TOP_P = float(os.getenv("REFORMULATOR_LLM_TOP_P", "0.9"))
        _max_tokens = os.getenv("REFORMULATOR_LLM_MAX_TOKENS")
        MAX_TOKENS: int | None = int(_max_tokens) if _max_tokens else None
        TIMEOUT = float(os.getenv("REFORMULATOR_LLM_TIMEOUT", "300"))

    # === Embedding ===

    class EMBEDDING:
        MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    # === Qdrant ===

    class QDRANT:
        HOST = os.environ["QDRANT_HOST"]
        PORT = int(os.getenv("QDRANT_PORT", "6333"))
        GRPC_PORT = int(os.getenv("QDRANT_GRPC_PORT", "6334"))

    class COLLECTIONS:
        QUESTIONS = "questions"
        TUTORING_NODES = "tutoring_nodes"

    class VECTOR:
        DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
        DISTANCE = "Cosine"

    class SEARCH:
        DEFAULT_TOP_K = int(os.getenv("CACHE_TOP_K", "5"))
        DEFAULT_THRESHOLD = 0.5
        HIGH_CONFIDENCE_THRESHOLD = 0.9
        MEDIUM_CONFIDENCE_THRESHOLD = 0.7

    class GRAPH:
        MAX_DEPTH = int(os.getenv("TUTORING_MAX_DEPTH", "4"))
        MAX_CHILDREN_PER_NODE = 5

    # === Routing ===

    CACHE_TOP_K = int(os.getenv("CACHE_TOP_K", "5"))

    class CONFIDENCE_TIERS:
        TIER_1_THRESHOLD = float(os.getenv("CONFIDENCE_TIER_1", "0.85"))
        TIER_2_THRESHOLD = float(os.getenv("CONFIDENCE_TIER_2", "0.70"))
        TIER_3_THRESHOLD = float(os.getenv("CONFIDENCE_TIER_3", "0.50"))

    # === Tutoring ===

    class TUTORING:
        MAX_INTERACTION_DEPTH = int(os.getenv("TUTORING_MAX_DEPTH", "5"))
        ENABLE_TUTORING_MODE = os.getenv("TUTORING_ENABLED", "true").lower() == "true"
        CACHE_THRESHOLD = float(os.getenv("TUTORING_INTERACTION_THRESHOLD", "0.85"))

    # === Input Processing ===

    class INPUT_PROCESSING:
        MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "5000"))
        STRIP_WHITESPACE = os.getenv("STRIP_WHITESPACE", "true").lower() == "true"

    # === Reformulation ===

    class REFORMULATION:
        USE_LLM = os.getenv("REFORMULATOR_USE_LLM", "true").lower() == "true"
        MAX_CONTEXT_MESSAGES = int(os.getenv("REFORMULATOR_MAX_CONTEXT", "5"))
        MAX_CONTEXT_LENGTH = int(os.getenv("REFORMULATOR_MAX_CONTEXT_LENGTH", "500"))

    # === Intent Classifier ===

    class CLASSIFIER:
        RULE_CONFIDENCE_THRESHOLD = float(
            os.getenv("INTENT_RULE_CONFIDENCE_THRESHOLD", "0.8")
        )
        USE_LLM_FALLBACK = (
            os.getenv("INTENT_USE_LLM_FALLBACK", "true").lower() == "true"
        )
        LLM_TEMPERATURE = float(os.getenv("INTENT_CLASSIFIER_LLM_TEMPERATURE", "0.1"))
        LLM_MAX_TOKENS = int(os.getenv("INTENT_CLASSIFIER_LLM_MAX_TOKENS", "50"))

    # === Session ===

    class SESSION:
        TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
        MAX_HISTORY_LENGTH = int(os.getenv("SESSION_MAX_HISTORY", "50"))

    class CLEANUP:
        INTERVAL_SECONDS = int(os.getenv("SESSION_CLEANUP_INTERVAL", "300"))
