from prometheus_client import Counter, Histogram

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

# Gateway-specific metrics
gateway_data_processing_duration_seconds = Histogram(
    "gateway_data_processing_duration_seconds",
    "Data Processing service call duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

gateway_answer_retrieval_duration_seconds = Histogram(
    "gateway_answer_retrieval_duration_seconds",
    "Answer Retrieval service call duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

gateway_errors_total = Counter(
    "gateway_errors_total",
    "Total errors in gateway",
    ["error_type"],
)
