from prometheus_client import Counter, Histogram

# HTTP request metrics
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

# Intent classifier specific metrics
classifications_total = Counter(
    "intent_classifications_total",
    "Total classifications by intent",
    ["intent"],
)

classification_method_total = Counter(
    "intent_classification_method_total",
    "Classifications by method",
    ["method"],
)

classification_confidence = Histogram(
    "intent_classification_confidence",
    "Distribution of classification confidence scores",
    buckets=[0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0],
)

llm_fallback_total = Counter(
    "intent_llm_fallback_total",
    "Times LLM fallback was used",
)

llm_fallback_errors_total = Counter(
    "intent_llm_fallback_errors_total",
    "Times LLM fallback failed",
)
