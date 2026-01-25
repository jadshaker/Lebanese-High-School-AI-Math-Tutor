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

# Cache service-specific metrics
cache_searches_total = Counter(
    "cache_searches_total",
    "Total cache search requests",
)

cache_saves_total = Counter(
    "cache_saves_total",
    "Total cache save requests",
)

cache_size_items = Gauge(
    "cache_size_items",
    "Number of items in cache",
)

cache_similarity_score = Histogram(
    "cache_similarity_score",
    "Cache similarity scores distribution",
    buckets=[0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0],
)
