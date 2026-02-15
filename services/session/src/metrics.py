from prometheus_client import Counter, Gauge, Histogram

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

# Session-specific metrics
sessions_active_total = Gauge(
    "session_active_total",
    "Number of currently active sessions",
)

sessions_created_total = Counter(
    "session_created_total",
    "Total sessions created",
)

sessions_expired_total = Counter(
    "session_expired_total",
    "Total sessions expired by cleanup",
)

sessions_deleted_total = Counter(
    "session_deleted_total",
    "Total sessions manually deleted",
)

session_phase_transitions = Counter(
    "session_phase_transitions_total",
    "Total phase transitions",
    ["from_phase", "to_phase"],
)

session_messages_total = Counter(
    "session_messages_total",
    "Total messages added to sessions",
    ["role"],
)

session_tutoring_depth = Histogram(
    "session_tutoring_depth",
    "Distribution of tutoring depths reached",
    buckets=[1, 2, 3, 4, 5],
)

session_duration_seconds = Histogram(
    "session_duration_seconds",
    "Session duration from creation to completion",
    buckets=[60, 300, 600, 1800, 3600, 7200],
)
