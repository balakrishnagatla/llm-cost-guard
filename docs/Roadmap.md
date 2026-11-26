# Roadmap

Ordered by expected savings, based on what the [test results](Results.md) showed.

## Done in v0.4

- ✅ Reasoning tokens tracked separately; low reasoning effort and output caps for the cheap tier
- ✅ Pre-call cost estimates for budgets
- ✅ Failover across providers

## Done in v0.5

- ✅ Per-call tracing, insights, Prometheus + Grafana, OpenTelemetry export
- ✅ Demo traffic generator

## Next: measure the reasoning savings

- Re-run the Groq test with reasoning control on and publish the before/after numbers in [Results](Results.md)
- Smarter routing: a small classifier instead of keywords, with the threshold tuned on real traffic

## Then: smarter savings

- **Semantic cache:** reuse answers to questions that mean the same thing, not only identical ones
- **Provider prompt caching:** track and price cached input tokens, which several providers bill at a discount
- **Batch routing:** send non-urgent jobs to providers' batch APIs, which are typically much cheaper

## Then: better control

- **Budget alerts** to Slack or email at 80% and 100%
- **Spend anomaly alerts:** flag a team whose spend jumps far above its normal pattern
- **Cost per outcome:** link spend to results (for example, cost per resolved support ticket)

## Platform

Production deployment (Helm chart for Kubernetes, Postgres and Redis for multiple replicas, cloud infrastructure as code) is developed in a companion repository: [llm-cost-guard-platform](https://github.com/balakrishnagatla/llm-cost-guard-platform). This repository stays the reference implementation and local prototype.
