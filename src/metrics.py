from prometheus_client import Counter, Gauge, Histogram

# === Common HTTP Metrics ===

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "endpoint", "method", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service", "endpoint", "method"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

service_health_status = Gauge(
    "service_health_status",
    "Current health status of the service (2=healthy, 1=degraded, 0=down)",
    ["service"],
)

# === Gateway / Pipeline Metrics ===

gateway_input_processor_duration_seconds = Histogram(
    "gateway_input_processor_duration_seconds",
    "Input Processor duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

gateway_reformulator_duration_seconds = Histogram(
    "gateway_reformulator_duration_seconds",
    "Reformulator duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

gateway_embedding_duration_seconds = Histogram(
    "gateway_embedding_duration_seconds",
    "Embedding call duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

gateway_cache_search_duration_seconds = Histogram(
    "gateway_cache_search_duration_seconds",
    "Cache search duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

gateway_small_llm_duration_seconds = Histogram(
    "gateway_small_llm_duration_seconds",
    "Small LLM call duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

gateway_large_llm_duration_seconds = Histogram(
    "gateway_large_llm_duration_seconds",
    "Large LLM call duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

gateway_cache_save_duration_seconds = Histogram(
    "gateway_cache_save_duration_seconds",
    "Cache save duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

gateway_llm_calls_total = Counter(
    "gateway_llm_calls_total",
    "Total LLM calls made",
    ["llm_service"],
)

gateway_cache_hits_total = Counter(
    "gateway_cache_hits_total",
    "Total cache hits (validated by Small LLM)",
)

gateway_cache_misses_total = Counter(
    "gateway_cache_misses_total",
    "Total cache misses",
)

gateway_confidence = Histogram(
    "gateway_confidence",
    "Confidence scores of results",
    buckets=[0, 0.5, 0.7, 0.85, 0.9, 0.95, 1.0],
)

gateway_errors_total = Counter(
    "gateway_errors_total",
    "Total errors",
    ["error_type"],
)

# === Embedding Metrics ===

embedding_dimensions = Gauge(
    "embedding_dimensions",
    "Configured embedding dimensions",
)

# === Vector Cache Metrics ===

cache_searches_total = Counter(
    "cache_searches_total",
    "Total cache search operations",
)

cache_search_hits_total = Counter(
    "cache_search_hits_total",
    "Total cache search hits",
)

cache_search_misses_total = Counter(
    "cache_search_misses_total",
    "Total cache search misses",
)

cache_saves_total = Counter(
    "cache_saves_total",
    "Total cache save operations",
)

cache_questions_total = Gauge(
    "cache_questions_total",
    "Total questions in cache",
)

cache_interactions_total = Gauge(
    "cache_interactions_total",
    "Total interactions in cache",
)

cache_similarity_score = Histogram(
    "cache_similarity_score",
    "Similarity scores for cache search results",
    buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0],
)

interaction_cache_hits_total = Counter(
    "interaction_cache_hits_total",
    "Total interaction cache hits",
)

interaction_cache_misses_total = Counter(
    "interaction_cache_misses_total",
    "Total interaction cache misses",
)

interaction_depth_histogram = Histogram(
    "interaction_depth_histogram",
    "Depth of interaction nodes",
    buckets=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
)

feedback_positive_total = Counter(
    "feedback_positive_total",
    "Total positive feedback",
)

feedback_negative_total = Counter(
    "feedback_negative_total",
    "Total negative feedback",
)

# === Intent Classifier Metrics ===

classifications_total = Counter(
    "classifications_total",
    "Total classifications",
    ["intent"],
)

classification_method_total = Counter(
    "classification_method_total",
    "Total classifications by method",
    ["method"],
)

classification_confidence = Histogram(
    "classification_confidence",
    "Classification confidence scores",
    buckets=[0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0],
)

llm_fallback_total = Counter(
    "llm_fallback_total",
    "Total LLM fallback classifications",
)

llm_fallback_errors_total = Counter(
    "llm_fallback_errors_total",
    "Total LLM fallback errors",
)

# === Session Metrics ===

sessions_active_total = Gauge(
    "sessions_active_total",
    "Currently active sessions",
)

sessions_created_total = Counter(
    "sessions_created_total",
    "Total sessions created",
)

sessions_expired_total = Counter(
    "sessions_expired_total",
    "Total sessions expired",
)

sessions_deleted_total = Counter(
    "sessions_deleted_total",
    "Total sessions deleted",
)

session_phase_transitions = Counter(
    "session_phase_transitions",
    "Session phase transitions",
    ["from_phase", "to_phase"],
)

session_messages_total = Counter(
    "session_messages_total",
    "Total session messages",
    ["role"],
)

session_tutoring_depth = Histogram(
    "session_tutoring_depth",
    "Tutoring interaction depth at session end",
    buckets=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
)

session_duration_seconds = Histogram(
    "session_duration_seconds",
    "Session duration in seconds",
    buckets=[60, 300, 600, 1800, 3600, 7200],
)
