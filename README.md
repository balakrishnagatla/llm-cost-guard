# LLM Cost Guard

A small proxy that sits between your app and LLM APIs. It **tracks what every call costs, by team and feature**, **caches repeat calls** so you don't pay twice for the same answer, and **routes simple prompts to cheaper models**.

```
your app ──► LLM Cost Guard ──► OpenAI / Anthropic / Groq / Gemini / Ollama
                 │
                 ├─ logs tokens, cost, latency per team & feature
                 ├─ serves repeat calls from cache ($0)
                 ├─ routes simple prompts to a cheaper model
                 └─ dashboard at http://localhost:8080
```

**📖 Full documentation: [docs/Home.md](docs/Home.md)** (the problem, how it works, test results, security, roadmap). Also published to the [project wiki](https://github.com/balakrishnagatla/llm-cost-guard/wiki).

## Features (v0.3)

- OpenAI-compatible endpoint (works with OpenAI, Groq, Gemini, OpenRouter, Ollama and other compatible APIs) and the Anthropic Messages API
- Cost per call from an editable `pricing.json`
- Tag calls with `X-Team` and `X-Feature` headers to see spend per team and feature
- Response cache (by default only `temperature: 0` calls, which are safe to reuse)
- Model routing with `"model": "auto"`: simple prompts go to a cheap model, complex ones to a strong model
- Streaming (`"stream": true`) for both APIs, with token usage captured and priced
- **Per-team daily budgets**: calls get HTTP 429 once a team hits its limit
- **Security built in**: per-team proxy keys, dashboard login, per-key cache isolation, localhost-only by default (see [Security](#security))
- Live dashboard with spend, cache savings, hit rate and latency
- `/stats` JSON endpoint for your own reporting

## Quick start

```bash
git clone https://github.com/balakrishnagatla/llm-cost-guard.git
cd llm-cost-guard
cp .env.example .env        # add your API key
docker compose up --build
```

Or without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8080
```

Open http://localhost:8080 for the dashboard.

## Make a call through the proxy

```bash
curl http://localhost:8080/openai/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "X-Team: search" -H "X-Feature: summarize" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "temperature": 0,
       "messages": [{"role": "user", "content": "Say hello"}]}'
```

Run it twice: the second response has `x-cost-guard-cache: hit` and costs $0.

With the OpenAI Python SDK, just change the base URL:

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8080/openai/v1",
                default_headers={"X-Team": "search", "X-Feature": "summarize"})
```

Anthropic: `POST http://localhost:8080/anthropic/v1/messages` with your usual `x-api-key` header.

## Model routing

Send `"model": "auto"` and the proxy picks the model for you, using the rules in `routing.json`:

- **Strong model** if the request uses tools, the prompt is longer than `max_cheap_prompt_chars`, or the last user message contains a keyword like "debug", "analyze" or "step by step"
- **Cheap model** otherwise

Requests that name a model are never rerouted. Each response tells you what happened:

```
x-cost-guard-model: gpt-4o-mini
x-cost-guard-route-reason: short, simple prompt
```

The dashboard shows **Saved by routing (est.)**: what the same tokens would have cost on the strong model minus what they cost on the cheap one. It's an estimate, since different models use slightly different token counts.

For Groq, set the models in `routing.json` to Groq model IDs, for example:

```json
"openai": { "cheap": "openai/gpt-oss-20b", "strong": "openai/gpt-oss-120b" }
```

(Groq's model list changes, so check console.groq.com/docs/models.)

## Streaming

Send `"stream": true` as usual. Chunks are passed straight through, and the proxy reads token usage from the stream to price the call. For OpenAI-compatible APIs it adds `stream_options.include_usage` automatically. Streamed calls are not cached.

## Use a free API for testing

Set `OPENAI_BASE_URL` in `.env` to any OpenAI-compatible provider:

| Provider | `OPENAI_BASE_URL` | Get a key |
|---|---|---|
| Groq | `https://api.groq.com/openai/v1` | console.groq.com/keys |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | aistudio.google.com |
| OpenRouter (`:free` models) | `https://openrouter.ai/api/v1` | openrouter.ai/keys |
| Ollama (local, no key) | `http://host.docker.internal:11434/v1` | ollama.com |

Free models cost $0, so to show realistic numbers in a demo, add the model to `pricing.json` with the price of the paid model it would replace.

## Security

LLM Cost Guard holds your provider API keys, so treat it like any other gateway.

| Protection | How |
|---|---|
| **Per-team proxy keys** | Set `COST_GUARD_KEYS=search:k_...,support:k_...`. Callers must send `X-Cost-Guard-Key`, and the team is taken from the key, so nobody can bill another team by faking `X-Team`. |
| **Dashboard login** | Set `DASHBOARD_PASSWORD` to protect the dashboard and `/stats` (HTTP Basic auth). |
| **Budgets** | `BUDGETS=search:5,support:2.50` caps daily spend per team (resets 00:00 UTC). The check runs before each call, so a team can go over by at most one call. Limits the damage from a leaked key or a runaway loop. |
| **Cache isolation** | Cached answers are scoped to the upstream API key, so one user never gets another's response. |
| **Localhost only** | `docker-compose.yml` binds to `127.0.0.1`. Expose it only with keys, a password and HTTPS in front. |
| **Hardened container** | Runs as a non-root user with all Linux capabilities dropped and `no-new-privileges`. |
| **Input limits** | Request bodies over `MAX_BODY_BYTES` are rejected; team/feature names are sanitized before they're stored or displayed. |
| **Safe headers** | CSP, `X-Frame-Options: DENY`, `nosniff`; API docs endpoints are disabled. |

Generate a proxy key:

```bash
python3 -c "import secrets; print('k_' + secrets.token_urlsafe(24))"
```

Call through a locked-down proxy:

```bash
curl http://localhost:8080/openai/v1/chat/completions \
  -H "X-Cost-Guard-Key: k_your_team_key" -H "X-Feature: summarize" \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Say hello"}]}'
```

Every pull request runs the tests, a dependency vulnerability check (`pip-audit`), a static security scan (`bandit`) and a Docker build. See [SECURITY.md](SECURITY.md) to report a vulnerability.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Upstream for the OpenAI-compatible route |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Upstream for the Anthropic route |
| `CACHE_MODE` | `deterministic` | `deterministic` (temperature 0 only), `all`, or `off` |
| `CACHE_TTL_SECONDS` | `86400` | How long cached responses stay valid |
| `DB_PATH` | `data/costguard.db` | SQLite file for logs and cache |
| `ROUTING_PATH` | `routing.json` | Routing rules for `"model": "auto"` |
| `COST_GUARD_KEYS` | (empty = dev mode) | Per-team proxy keys, `team:key,...` |
| `DASHBOARD_PASSWORD` | (empty = open) | Password for the dashboard and `/stats` |
| `BUDGETS` | (empty) | Daily USD limit per team, `team:amount,...` |
| `MAX_BODY_BYTES` | `1000000` | Largest request body accepted |

Prices in `pricing.json` are examples (USD per 1M tokens). Check them against each provider's pricing page.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Roadmap

- [x] Streaming responses
- [x] Model routing: send simple prompts to cheaper models
- [x] Budgets per team
- [ ] Budget alerts (Slack/email)
- [ ] Semantic cache (similar prompts, not just identical ones)
- [ ] Prometheus metrics and a Grafana dashboard

## Notes

- The cache is shared by everyone using the proxy. Run one proxy per trust boundary.
- Never commit your `.env` file or API keys. `.gitignore` already excludes `.env`.
