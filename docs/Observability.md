# Observability

LLM Cost Guard gives you three views of what's happening, from simplest to most powerful.

| Layer | What it answers | Where |
|---|---|---|
| **Built-in dashboard** | What did we spend, what did we save, and what happened to each call? | http://localhost:8080 |
| **Prometheus + Grafana** | How are spend, savings, latency and errors trending over time? Alert me when something spikes. | http://localhost:3000 |
| **OpenTelemetry + Jaeger** | Show me the timeline of one request, alongside the rest of my system's traces. | http://localhost:16686 |

## 1. Built-in dashboard

No setup needed. Besides spend by team, feature and model, it shows:

- **Savings rate:** the share of spend avoided by the cache and routing
- **Spend over 24 hours,** hour by hour, with savings stacked on top
- **Most expensive calls,** and **average cost per call by feature**
- **Reasoning share of output by model:** how much you pay for hidden thinking
- **Latency by upstream** (p50 and p95)
- **Blocked by budget** and **errors** counters
- **Recent calls:** click any row to see its trace

### Traces

Every call gets a request ID, returned in the `x-request-id` header, and a trace of each step it went through:

```
✓ auth      team analytics
✓ route     auto -> openai/gpt-oss-120b (strong: keyword 'analyze')
✓ estimate  up to $0.00061725 (no budget set)
✓ cache     miss
✗ upstream  primary (openai/gpt-oss-120b) -> HTTP 429          (1.8 ms)
✓ upstream  backup (gemini-2.5-flash) -> HTTP 200              (214 ms)
✓ result    89 in / 249 out (235 reasoning) = $0.000109
```

Look up any call with `GET /calls/<request-id>`, or list recent ones with `GET /calls?limit=50`.

## 2. Prometheus + Grafana

Start the gateway with the observability stack:

```bash
docker compose --profile observability up -d --build
```

- **Grafana:** http://localhost:3000 opens straight to the *LLM Cost Guard* dashboard: spend and savings, savings rate, cache hit rate, spend per hour by team, calls by model, reasoning share, p95 latency, upstream errors, budget refusals and budget remaining.
- **Prometheus:** http://localhost:9090 for ad-hoc queries.

Metrics exposed at `/metrics`:

| Metric | Labels | Meaning |
|---|---|---|
| `costguard_requests_total` | team, feature, model, upstream, status, cache | Calls handled |
| `costguard_cost_usd_total` | team, feature, model | Spend |
| `costguard_saved_usd_total` | team, kind (cache, routing) | Spend avoided |
| `costguard_tokens_total` | model, kind (input, output, reasoning) | Tokens |
| `costguard_request_duration_seconds` | upstream | Latency histogram |
| `costguard_upstream_errors_total` | upstream, reason | Failed attempts (trigger failover) |
| `costguard_budget_usd`, `costguard_budget_remaining_usd` | team | Daily budget and what's left |

Example alert: page someone when a team spends more than $5 in an hour:

```
sum by (team) (increase(costguard_cost_usd_total[1h])) > 5
```

Set `METRICS_TOKEN` to require a bearer token on `/metrics` (and add it to `observability/prometheus.yml`).

## 3. OpenTelemetry + Jaeger

Turn on trace export by pointing the gateway at an OpenTelemetry collector:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318 docker compose --profile observability up -d --build
```

Open Jaeger at http://localhost:16686 and pick the `llm-cost-guard` service. Each call is an `llm.request` span with a child span per step (auth, route, budget, cache, each upstream attempt, result). Spans use the OpenTelemetry **GenAI** attribute names (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`), plus `costguard.*` attributes for team, feature, cost and savings, so they fit alongside traces from the rest of your system. Any OTLP-compatible backend works (Grafana Tempo, Honeycomb, Datadog and others).

Export is off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

## Try it with demo traffic

Fill every view with realistic data, for free (needs Python 3.12 and `pip install -r requirements.txt`):

```bash
python scripts/demo_traffic.py
```

This starts a separate demo gateway on http://localhost:8090 with a simulated provider: several teams and features, cheap and strong routing, cache hits, streaming, failover to a backup provider and a team that runs out of budget. Your real data isn't touched.

To send traffic through your real gateway and Groq instead, which also fills Grafana and Jaeger (paced to stay within the free tier):

```bash
python scripts/demo_traffic.py --mode real
```
