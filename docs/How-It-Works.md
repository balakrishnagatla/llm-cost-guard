# How It Works

## Architecture

```
                        ┌────────────────────────── LLM Cost Guard ──────────────────────────┐
 App (team: search) ──► │ 1. Authenticate ─► 2. Route ─────────► 3. Estimate cost ─────────► │
   X-Cost-Guard-Key     │    (team = key)    (cheap: low          & check budget             │
   X-Feature: ...       │                     reasoning effort,   (429 before spending)      │
                        │                     output cap)                │                   │
                        │                                                ▼                   │
                        │ 4. Cache lookup ── hit ──► answer at $0                            │
                        │        │ miss                                                      │
                        │        ▼                                                           │
                        │ 5. Forward ──────────────────────────────────────────────────────► │ ──► AI provider
                        │        │ 429 / 5xx / unreachable                                   │     (Groq, OpenAI, ...)
                        │        └─────────────────────────────────────────────────────────► │ ──► backup provider
                        │ 6. Price tokens (incl. reasoning)                                  │     (Gemini, ...)
                        │ 7. Log team, feature, model, upstream, tokens, cost, savings       │
                        │                                                                    │
                        │ SQLite ◄── /stats ◄── Dashboard (password)                          │
                        └────────────────────────────────────────────────────────────────────┘
```

Adopting it is a one-line change: point your app's base URL at the gateway instead of the provider.

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8080/openai/v1",
                default_headers={"X-Cost-Guard-Key": "k_...", "X-Feature": "summarize"})
```

## The request, step by step

1. **Authenticate.** The caller sends its team's proxy key. The team is read from the key, so it can't be faked with a header.
2. **Route.** If the app asked for `"model": "auto"`, the gateway picks a model:
   - **Strong model** when the request uses tools, the prompt is long, or it contains words like "analyze", "debug" or "step by step"
   - **Cheap model** for everything else, sent with **low reasoning effort and an output cap** (tier settings in `routing.json`; the caller's own settings always win)

   Rules live in `routing.json`, so they can change without code changes. Apps that name a model are never rerouted.
3. **Estimate and budget check.** The gateway estimates the call's cost before sending it (prompt size plus the output limit). If that would push the team over its daily budget, the call is refused with HTTP 429 and nothing is spent. Other teams keep working.
4. **Cache.** Identical deterministic requests (`temperature: 0`) are answered from the cache at no cost. Cache entries are tied to the caller's API key, so answers never cross users.
5. **Forward, with failover.** The request goes to the provider. If it answers 429 or 5xx, or can't be reached, the gateway retries on the backup providers listed under `fallbacks` in `routing.json`, mapping the model name. Streaming responses are passed through chunk by chunk.
6. **Price.** Token counts from the provider's response are multiplied by prices in `pricing.json`. Reasoning tokens are recorded separately; when a provider reports 0 but returns reasoning text (Groq does this), they're estimated from that text.
7. **Log.** Every call is recorded with team, feature, model, upstream, tokens, reasoning tokens, cost, latency and how much the cache or routing saved.

## Components

| Part | File | Role |
|---|---|---|
| Gateway | `app/main.py` | Request flow, streaming, provider adapters |
| Routing | `app/router.py` + `routing.json` | Picks cheap vs strong model, tier settings, fallbacks |
| Pricing | `app/pricing.py` + `pricing.json` | USD per million tokens per model |
| Security | `app/security.py` | Keys, dashboard login, budgets, input cleaning |
| Storage | `app/db.py` | Call log and cache in SQLite |
| Dashboard | `app/dashboard.html` | Live spend, savings, budgets |

## How savings are measured

- **Saved by cache:** what the cached answer would have cost if it had gone to the provider again.
- **Saved by routing (estimate):** the same tokens priced on the strong model, minus what they cost on the cheap one. It's an estimate because different models produce slightly different token counts.
