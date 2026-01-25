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

# Data Processing-specific metrics
data_processing_input_processor_duration_seconds = Histogram(
    "data_processing_input_processor_duration_seconds",
    "Input Processor service call duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

data_processing_reformulator_duration_seconds = Histogram(
    "data_processing_reformulator_duration_seconds",
    "Reformulator service call duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)
