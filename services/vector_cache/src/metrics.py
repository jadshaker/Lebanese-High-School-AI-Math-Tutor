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

# Vector cache specific metrics
cache_searches_total = Counter(
    "vector_cache_searches_total",
    "Total cache search requests",
)

cache_search_hits_total = Counter(
    "vector_cache_search_hits_total",
    "Total cache search hits (found results above threshold)",
)

cache_search_misses_total = Counter(
    "vector_cache_search_misses_total",
    "Total cache search misses (no results above threshold)",
)

cache_saves_total = Counter(
    "vector_cache_saves_total",
    "Total cache save requests",
)

cache_questions_total = Gauge(
    "vector_cache_questions_total",
    "Total number of questions in cache",
)

cache_interactions_total = Gauge(
    "vector_cache_interactions_total",
    "Total number of tutoring interaction nodes in cache",
)

cache_similarity_score = Histogram(
    "vector_cache_similarity_score",
    "Cache similarity scores distribution",
    buckets=[0, 0.5, 0.7, 0.85, 0.9, 0.95, 1.0],
)

# Interaction-specific metrics
interaction_cache_hits_total = Counter(
    "vector_cache_interaction_hits_total",
    "Total tutoring interaction cache hits",
)

interaction_cache_misses_total = Counter(
    "vector_cache_interaction_misses_total",
    "Total tutoring interaction cache misses",
)

interaction_depth_histogram = Histogram(
    "vector_cache_interaction_depth",
    "Distribution of tutoring interaction depths",
    buckets=[1, 2, 3, 4, 5],
)

# Feedback metrics
feedback_positive_total = Counter(
    "vector_cache_feedback_positive_total",
    "Total positive feedback received",
)

feedback_negative_total = Counter(
    "vector_cache_feedback_negative_total",
    "Total negative feedback received",
)
