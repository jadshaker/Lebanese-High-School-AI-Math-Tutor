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

# Answer Retrieval-specific metrics
answer_retrieval_llm_calls_total = Counter(
    "answer_retrieval_llm_calls_total",
    "Total LLM calls made by answer retrieval service",
    ["llm_service"],
)

answer_retrieval_cache_hits_total = Counter(
    "answer_retrieval_cache_hits_total",
    "Total cache hits (exact matches with similarity >= 0.95)",
)

answer_retrieval_cache_misses_total = Counter(
    "answer_retrieval_cache_misses_total",
    "Total cache misses (no exact match, required large LLM call)",
)

answer_retrieval_confidence = Histogram(
    "answer_retrieval_confidence",
    "Confidence scores of answer retrieval results",
    buckets=[0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0],
)
