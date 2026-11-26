# LLM Cost Guard

A small proxy that sits between your app and LLM APIs. It **tracks what every call costs, by team and feature**, and **caches repeat calls** so you don't pay twice for the same answer.

```
your app ──► LLM Cost Guard ──► OpenAI / Anthropic / Groq / Gemini / Ollama
                 │
                 ├─ logs tokens, cost, latency per team & feature
                 ├─ serves repeat calls from cache ($0)
                 └─ dashboard at http://localhost:8080
```

## Features (v0.1)

- OpenAI-compatible endpoint (works with OpenAI, Groq, Gemini, OpenRouter, Ollama and other compatible APIs) and the Anthropic Messages API
- Cost per call from an editable `pricing.json`
- Tag calls with `X-Team` and `X-Feature` headers to see spend per team and feature
- Response cache (by default only `temperature: 0` calls, which are safe to reuse)
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

## Use a free API for testing

Set `OPENAI_BASE_URL` in `.env` to any OpenAI-compatible provider:

| Provider | `OPENAI_BASE_URL` | Get a key |
|---|---|---|
| Groq | `https://api.groq.com/openai/v1` | console.groq.com/keys |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | aistudio.google.com |
| OpenRouter (`:free` models) | `https://openrouter.ai/api/v1` | openrouter.ai/keys |
| Ollama (local, no key) | `http://host.docker.internal:11434/v1` | ollama.com |

Free models cost $0, so to show realistic numbers in a demo, add the model to `pricing.json` with the price of the paid model it would replace.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Upstream for the OpenAI-compatible route |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Upstream for the Anthropic route |
| `CACHE_MODE` | `deterministic` | `deterministic` (temperature 0 only), `all`, or `off` |
| `CACHE_TTL_SECONDS` | `86400` | How long cached responses stay valid |
| `DB_PATH` | `data/costguard.db` | SQLite file for logs and cache |

Prices in `pricing.json` are examples (USD per 1M tokens). Check them against each provider's pricing page.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Roadmap

- [ ] Streaming responses
- [ ] Model routing: send simple prompts to cheaper models
- [ ] Budgets and alerts per team
- [ ] Semantic cache (similar prompts, not just identical ones)
- [ ] Prometheus metrics and a Grafana dashboard

## Notes

- The cache is shared by everyone using the proxy. Run one proxy per trust boundary.
- Streaming isn't supported yet. Requests with `"stream": true` return 400.
