from prometheus_client import Counter, Gauge, Histogram

# HTTP request metrics (common across all services)
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

# Service health status (2=healthy, 1=degraded, 0=down)
service_health_status = Gauge(
    "service_health_status",
    "Current health status of the service (2=healthy, 1=degraded, 0=down)",
    ["service"],
)

# Gateway-specific metrics - Phase 1 (Input Processing)
gateway_input_processor_duration_seconds = Histogram(
    "gateway_input_processor_duration_seconds",
    "Input Processor service call duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

gateway_reformulator_duration_seconds = Histogram(
    "gateway_reformulator_duration_seconds",
    "Reformulator service call duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# Gateway-specific metrics - Phase 2 (Answer Retrieval)
gateway_embedding_duration_seconds = Histogram(
    "gateway_embedding_duration_seconds",
    "Embedding service call duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

gateway_cache_search_duration_seconds = Histogram(
    "gateway_cache_search_duration_seconds",
    "Cache search duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

gateway_small_llm_duration_seconds = Histogram(
    "gateway_small_llm_duration_seconds",
    "Small LLM service call duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

gateway_large_llm_duration_seconds = Histogram(
    "gateway_large_llm_duration_seconds",
    "Large LLM service call duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

gateway_cache_save_duration_seconds = Histogram(
    "gateway_cache_save_duration_seconds",
    "Cache save duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

gateway_llm_calls_total = Counter(
    "gateway_llm_calls_total",
    "Total LLM calls made by gateway",
    ["llm_service"],
)

gateway_cache_hits_total = Counter(
    "gateway_cache_hits_total",
    "Total cache hits (exact matches with similarity >= 0.95)",
)

gateway_cache_misses_total = Counter(
    "gateway_cache_misses_total",
    "Total cache misses (no exact match, required large LLM call)",
)

gateway_confidence = Histogram(
    "gateway_confidence",
    "Confidence scores of gateway results",
    buckets=[0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0],
)

gateway_errors_total = Counter(
    "gateway_errors_total",
    "Total errors in gateway",
    ["error_type"],
)
