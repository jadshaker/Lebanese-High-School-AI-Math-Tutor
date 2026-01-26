# Observability Stack Documentation

Complete guide to logging, metrics, and monitoring for the Lebanese High School AI Math Tutor.

## 📋 Overview

The observability stack consists of three components:

1. **Structured Logging** - JSON logs with request tracing
2. **Prometheus** - Metrics collection and storage
3. **Grafana** - Metrics visualization and dashboards

All 8 microservices are instrumented with comprehensive logging and metrics.

---

## 🔍 Structured Logging

### Features

- **JSON Format**: Easy parsing and analysis
- **Request Tracing**: Unique request IDs across the entire pipeline
- **Dual Output**:
  - Console (stdout) for Docker logs
  - Files with daily rotation for persistence
- **Log Retention**: 7 days of rotated logs
- **Levels**: DEBUG, INFO, WARNING, ERROR

### Log Format

```json
{
  "timestamp": "2026-01-24T10:30:45.123Z",
  "service": "gateway",
  "level": "INFO",
  "request_id": "req-abc123def456",
  "message": "Processing chat completion",
  "context": {
    "endpoint": "/v1/chat/completions",
    "method": "POST",
    "user_message": "What is x^2?"
  }
}
```

### Accessing Logs

#### Option 1: Docker Logs (Console Output)

```bash
# View all services
docker compose logs -f

# View specific service
docker compose logs -f gateway

# View last 100 lines
docker compose logs --tail=100 gateway

# Search for request ID
docker compose logs | grep "req-abc123"

# View only errors
docker compose logs | grep '"level":"ERROR"'
```

#### Option 2: Log Files (Persistent)

Log files are saved to `./.logs/<service-name>/app.log`:

```bash
# View gateway logs
tail -f .logs/gateway/app.log

# View last 100 lines
tail -n 100 .logs/gateway/app.log

# Search for errors in all services
grep -r '"level":"ERROR"' .logs/

# View specific service log
cat .logs/data_processing/app.log

# Follow multiple services
tail -f .logs/gateway/app.log .logs/answer_retrieval/app.log
```

#### Log File Locations

```
.logs/
├── gateway/app.log
├── large_llm/app.log
├── small_llm/app.log
├── embedding/app.log
├── cache/app.log
├── input_processor/app.log
├── fine_tuned_model/app.log
└── reformulator/app.log
```

#### Log Rotation

- **When**: Daily at midnight
- **Retention**: 7 days
- **Format**: `app.log.YYYY-MM-DD`
- **Automatic**: Old logs are deleted after 7 days

### Request Tracing

Request IDs flow through the entire pipeline:

```
User Request → Gateway (req-abc123)
  → Input Processor (req-abc123)
  → Reformulator (req-abc123)
  → Embedding (req-abc123)
  → Cache (req-abc123)
  → Small LLM (req-abc123)
  → Large LLM (req-abc123)
```

Search across all services:

```bash
# Find all logs for a specific request
grep "req-abc123" .logs/*/app.log

# Docker logs
docker compose logs | grep "req-abc123"
```

---

## 📊 Prometheus Metrics

### Accessing Prometheus

**URL**: http://localhost:9090

### Common Metrics Queries

#### Request Rate by Service

```promql
rate(http_requests_total[1m])
```

#### Request Latency (P95)

```promql
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m]))
```

#### Error Rate

```promql
rate(http_requests_total{status=~"5.."}[1m])
```

#### Cache Hit Rate

```promql
rate(gateway_cache_hits_total[1m]) /
(rate(gateway_cache_hits_total[1m]) + rate(gateway_cache_misses_total[1m]))
```

#### LLM Usage

```promql
# Small LLM calls
rate(gateway_llm_calls_total{llm_service="small_llm"}[1m])

# Large LLM calls
rate(gateway_llm_calls_total{llm_service="large_llm"}[1m])
```

#### Token Usage (Cost Tracking)

```promql
# Total tokens per minute
rate(llm_tokens_total[1m])

# By type
rate(llm_tokens_total{type="prompt"}[1m])
rate(llm_tokens_total{type="completion"}[1m])
```

### Available Metrics by Service

#### All Services (Common)

- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request latency histogram

#### Gateway

- `gateway_phase1_duration_seconds` - Phase 1 (data processing) duration
- `gateway_phase2_duration_seconds` - Phase 2 (answer retrieval) duration
- `gateway_llm_calls_total` - LLM usage (small/large)
- `gateway_cache_hits_total` - Cache hits
- `gateway_cache_misses_total` - Cache misses
- `gateway_errors_total` - Error count by type

#### LLM Services (small_llm, large_llm, fine_tuned_model)

- `llm_requests_total` - Request count by model
- `llm_tokens_total` - Token usage (prompt + completion)
- `llm_latency_seconds` - LLM response time

#### Embedding

- `embedding_requests_total` - Embedding requests by model
- `embedding_dimensions` - Vector dimensions (1536)
- `embedding_latency_seconds` - API call latency

#### Cache

- `cache_searches_total` - Search operations
- `cache_saves_total` - Save operations
- `cache_size_items` - Number of cached items
- `cache_similarity_score` - Similarity score distribution

### Metrics Endpoints

Each service exposes metrics at `/metrics`:

- Gateway: http://localhost:8000/metrics
- Large LLM: http://localhost:8001/metrics
- Embedding: http://localhost:8002/metrics
- Cache: http://localhost:8003/metrics
- Input Processor: http://localhost:8004/metrics
- Small LLM: http://localhost:8005/metrics
- Fine-Tuned Model: http://localhost:8006/metrics
- Reformulator: http://localhost:8007/metrics

---

## 📈 Grafana Dashboards

### Accessing Grafana

**URL**: http://localhost:3001

**Login**:
- Username: `admin`
- Password: `admin`

### Math Tutor Observability Dashboard

Pre-configured dashboard with 9 panels:

1. **Request Rate by Service** - Real-time requests per second
2. **Request Latency (P50, P95, P99)** - Percentile latencies
3. **Error Rate** - 5xx responses gauge
4. **Cache Performance** - Hits vs misses
5. **LLM Usage** - Small LLM vs Large LLM calls
6. **Token Usage** - Prompt and completion tokens
7. **Service Health** - Up/down status for all services
8. **Gateway Phase Duration** - Phase 1 & 2 latency (P95)
9. **LLM Latency** - LLM response time (P95)

### Dashboard Features

- **Auto-refresh**: Updates every 5 seconds
- **Time range**: Default 15 minutes, customizable
- **Filtering**: Filter by service, endpoint, status
- **Alerts**: Can be configured for critical metrics

---

## 🧪 Testing the Observability Stack

### 1. Start Services

```bash
docker compose up --build
```

Wait for all services to be healthy.

### 2. Generate Test Traffic

```bash
# Send 100 requests
for i in {1..100}; do
  curl -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
      "model": "math-tutor",
      "messages": [{"role": "user", "content": "What is 2+2?"}]
    }'
  echo "Request $i sent"
  sleep 0.5
done
```

### 3. Verify Logs

```bash
# Check JSON logs in console
docker compose logs --tail=20 gateway

# Check persistent log files
tail -n 20 .logs/gateway/app.log

# Verify request tracing (use actual request ID from logs)
grep "req-abc123" .logs/*/app.log
```

### 4. Verify Metrics

```bash
# Check metrics endpoint
curl http://localhost:8000/metrics | head -30

# Open Prometheus
open http://localhost:9090

# Run query: http_requests_total{service="gateway"}
```

### 5. Verify Grafana Dashboard

```bash
# Open Grafana
open http://localhost:3001

# Login: admin/admin
# Navigate to: Dashboards → Math Tutor Observability Dashboard
# Watch metrics update in real-time
```

---

## 🔧 Troubleshooting

### Logs Not Appearing in Files

```bash
# Check if log directory exists
ls -la .logs/gateway/

# Check container has write permissions
docker exec math-tutor-gateway ls -la /app/.logs/

# Check for errors in container
docker compose logs gateway | grep -i error
```

### Prometheus Not Scraping Services

```bash
# Check Prometheus targets
open http://localhost:9090/targets

# Services should show "UP" status
# If DOWN, check service health:
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

### Grafana Dashboard Not Showing Data

```bash
# Check Prometheus datasource
# Grafana → Configuration → Data sources → Prometheus
# Should point to: http://prometheus:9090

# Test connection - should show "Data source is working"

# Check if metrics exist in Prometheus
open http://localhost:9090
# Run: http_requests_total
```

### High Disk Usage from Logs

```bash
# Check log sizes
du -sh .logs/*/

# Logs rotate daily and keep 7 days
# Old logs auto-delete after 7 days

# Manual cleanup (if needed)
find .logs -name "*.log.*" -mtime +7 -delete
```

---

## 📌 Best Practices

### Logging

1. **Use request IDs**: Always include request_id when calling downstream services
2. **Log at appropriate levels**:
   - INFO: Normal operations
   - WARNING: Degraded but functional
   - ERROR: Failures that need attention
3. **Include context**: Add relevant data to context dict
4. **Avoid sensitive data**: Don't log API keys, passwords, PII

### Metrics

1. **Use labels wisely**: Don't create too many unique label combinations
2. **Histogram buckets**: Adjust buckets based on actual latencies
3. **Counter vs Gauge**: Counters for cumulative, gauges for point-in-time
4. **Rate queries**: Use `rate()` for counters, not raw values

### Monitoring

1. **Set up alerts**: Configure Prometheus alerts for critical metrics
2. **Review dashboards**: Regularly check Grafana for anomalies
3. **Correlate logs and metrics**: Use request IDs to trace issues
4. **Monitor costs**: Track LLM token usage for budget planning

---

## 🚀 Advanced Features (Optional)

### Add Custom Metrics

Edit `services/<service>/src/metrics.py`:

```python
from prometheus_client import Counter

custom_metric = Counter(
    'my_custom_metric',
    'Description of metric',
    ['label1', 'label2']
)

# In your code
custom_metric.labels(label1='value1', label2='value2').inc()
```

### Export Logs to External System

Logs are in JSON format for easy export to:
- **ELK Stack** (Elasticsearch, Logstash, Kibana)
- **Loki** (Grafana's log aggregation)
- **Datadog**, **New Relic**, **CloudWatch**

### Set Up Alerting

Create `prometheus/alert_rules.yml`:

```yaml
groups:
  - name: math_tutor_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
```

---

## 📚 Quick Reference

### Log Commands

```bash
# Docker logs
docker compose logs -f <service>
docker compose logs | grep "req-<id>"
docker compose logs | grep '"level":"ERROR"'

# File logs
tail -f .logs/<service>/app.log
grep "req-<id>" .logs/*/app.log
grep -r '"level":"ERROR"' .logs/
```

### Prometheus Queries

```promql
# Request rate
rate(http_requests_total[1m])

# Latency P95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m]))

# Error rate
rate(http_requests_total{status=~"5.."}[1m])

# Cache hit rate
rate(gateway_cache_hits_total[1m]) / (rate(gateway_cache_hits_total[1m]) + rate(gateway_cache_misses_total[1m]))
```

### Access Points

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3001 (admin/admin)
- **Metrics Endpoints**: http://localhost:<port>/metrics
- **Log Files**: `./.logs/<service>/app.log`

---

## ✅ Checklist

After deployment, verify:

- [ ] All services healthy: `docker compose ps`
- [ ] Logs appearing in files: `ls -la .logs/gateway/`
- [ ] Prometheus scraping: http://localhost:9090/targets
- [ ] Grafana accessible: http://localhost:3001
- [ ] Dashboard showing data: Check Math Tutor dashboard
- [ ] Request tracing working: Test with `grep "req-<id>" .logs/*/app.log`

---

**Observability Stack Version**: 1.0
**Last Updated**: 2026-01-25
**Services Instrumented**: 8/8 ✅
