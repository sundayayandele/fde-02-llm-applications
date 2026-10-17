# Monitoring

| File | Purpose |
| --- | --- |
| `prometheus.yml` | Scrapes the API's `/metrics/` endpoint in the Compose `observability` profile |
| `alerts.yml` | Service down, 5xx rate above 5%, p95 latency above 1 s |
| `grafana/` | Datasource and an overview dashboard, provisioned automatically |

```bash
docker compose -f deploy/compose/compose.yaml --profile observability up -d --build
# Prometheus http://127.0.0.1:9090 · Grafana http://127.0.0.1:3000 (anonymous viewer)
```

Phase repos add their own metrics (for example ingest throughput, eval scores, tokens and cost
per request) and extend the dashboard. On Kubernetes, scrape with the `prometheus.io/*`
annotations already on the pods, or add a ServiceMonitor for the Prometheus Operator.
