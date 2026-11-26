# Roadmap

Ordered by expected savings, based on what the [test results](Results.md) showed.

## Next: control reasoning cost

Reasoning tokens were the biggest cost driver, so this comes first.

- **Track reasoning tokens separately** on the dashboard, where the provider reports them
- **Reasoning effort per tier:** send low reasoning effort to the cheap tier and let the strong tier think
- **Output caps per tier:** a maximum output length for simple routes, so a short question can't produce a long, expensive answer

## Then: smarter savings

- **Semantic cache:** reuse answers to questions that mean the same thing, not only identical ones
- **Provider prompt caching:** track and price cached input tokens, which several providers bill at a discount
- **Batch routing:** send non-urgent jobs to providers' batch APIs, which are typically much cheaper
- **Failover across providers:** if one provider is rate-limited or down, retry on another

## Then: better control

- **Pre-call cost estimate** so budgets can stop a call before it overspends, not after
- **Budget alerts** to Slack or email at 80% and 100%
- **Spend anomaly alerts:** flag a team whose spend jumps far above its normal pattern
- **Cost per outcome:** link spend to results (for example, cost per resolved support ticket)

## Platform

- Prometheus metrics and a Grafana dashboard
- Postgres option for multi-instance deployments
- Helm chart for Kubernetes
