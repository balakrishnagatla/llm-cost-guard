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

## Quality bar

- 17 automated tests, including 10 security tests
- End-to-end test with every protection enabled, probing the gateway as an attacker would
