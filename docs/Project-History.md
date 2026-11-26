# Project History

## v0.1: Measure

**Goal:** see what every call costs.

- Proxy for OpenAI-compatible APIs and Anthropic
- Cost per call from an editable price list
- Spend by team and feature via request headers
- Response cache for repeat deterministic calls
- Live dashboard and `/stats` endpoint
- Docker setup and tests

## v0.2: Save

**Goal:** cut spend automatically.

- **Model routing:** `"model": "auto"` sends simple prompts to a cheap model and complex ones to a strong model
- Estimated routing savings on the dashboard
- **Streaming** support, with token usage read from the stream
- Automatic database upgrade from v0.1

First real test against Groq: routing, caching and cost tracking all worked, and revealed that reasoning tokens dominate cost (see [Results](Results.md)).

## v0.3: Secure and control

**Goal:** make it safe to run for a real team.

- Fixed a stored XSS issue in the dashboard
- Per-team proxy keys, dashboard login, per-key cache isolation
- **Daily budgets per team**
- Request size limits, security headers, hardened Docker container, localhost-only by default
- CI on every pull request: tests, dependency audit, static security scan, Docker build
- Dependabot, branch protection, secret scanning, private vulnerability reporting
- Dependencies updated (FastAPI, Uvicorn, HTTPX, pytest, GitHub Actions)

## v0.4: Cut reasoning cost, stay up

**Goal:** act on the test finding that reasoning tokens dominate cost, and keep working when a provider fails.

- **Reasoning control:** the cheap tier is sent `reasoning_effort: low` and an output cap; reasoning tokens are tracked per call, team and model (estimated from reasoning text when the provider reports 0)
- **Pre-call cost estimates:** budgets stop a call before it overspends, not after
- **Failover:** retries on backup providers (for example Groq to Gemini) on rate limits, server errors and outages
- **Live smoke test** against the real Groq API, using a GitHub environment secret
- Defaults now target Groq's free tier, so the project runs at no cost out of the box
- MIT license, dashboard screenshot, lint and type checks, coverage floor, Docker named volume

## Quality bar

- 31 automated tests (security, routing, reasoning control, budgets, failover, streaming); 92% coverage
- Lint, type checks, dependency audit and static security scan on every pull request
- Live test against the real provider on every merge to `main`
- End-to-end test with every protection enabled, probing the gateway as an attacker would
