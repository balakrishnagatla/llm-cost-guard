# How It Works

## Architecture

```
                         ┌──────────────────── LLM Cost Guard ────────────────────┐
                         │                                                        │
 App (team: search) ───► │  1. Authenticate  ─►  2. Budget check  ─►  3. Route    │ ───► AI provider
   X-Cost-Guard-Key      │     (team = key)       (429 if over)       (cheap or   │      (Groq, OpenAI,
   X-Feature: summarize  │                                             strong)    │       Anthropic, ...)
                         │                                                │       │
                         │  4. Cache lookup ── hit ──► return answer, $0  │       │
                         │        │ miss                                  ▼       │
                         │        └──────────────► 5. Forward call, read usage    │
                         │                                    │                   │
                         │  6. Price the tokens ◄─────────────┘                   │
                         │  7. Log: team, feature, model, tokens, cost, savings   │
                         │                                                        │
                         │  SQLite ◄──── /stats ◄──── Dashboard (password)        │
                         └────────────────────────────────────────────────────────┘
```

Adopting it is a one-line change: point your app's base URL at the gateway instead of the provider.

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8080/openai/v1",
                default_headers={"X-Cost-Guard-Key": "k_...", "X-Feature": "summarize"})
```

## The request, step by step

1. **Authenticate.** The caller sends its team's proxy key. The team is read from the key, so it can't be faked with a header.
2. **Budget check.** If the team has a daily budget and has already spent it, the call is refused with HTTP 429. Other teams keep working.
3. **Route.** If the app asked for `"model": "auto"`, the gateway picks a model:
   - **Strong model** when the request uses tools, the prompt is long, or it contains words like "analyze", "debug" or "step by step"
   - **Cheap model** for everything else

   Rules live in `routing.json`, so they can change without code changes. Apps that name a model are never rerouted.
4. **Cache.** Identical deterministic requests (`temperature: 0`) are answered from the cache at no cost. Cache entries are tied to the caller's API key, so answers never cross users.
5. **Forward.** The request goes to the provider unchanged. Streaming responses are passed through chunk by chunk.
6. **Price.** Token counts from the provider's response are multiplied by prices in `pricing.json`.
7. **Log.** Every call is recorded with team, feature, model, tokens, cost, latency and how much the cache or routing saved.

## Components

| Part | File | Role |
|---|---|---|
| Gateway | `app/main.py` | Request flow, streaming, provider adapters |
| Routing | `app/router.py` + `routing.json` | Picks cheap vs strong model |
| Pricing | `app/pricing.py` + `pricing.json` | USD per million tokens per model |
| Security | `app/security.py` | Keys, dashboard login, budgets, input cleaning |
| Storage | `app/db.py` | Call log and cache in SQLite |
| Dashboard | `app/dashboard.html` | Live spend, savings, budgets |

## How savings are measured

- **Saved by cache:** what the cached answer would have cost if it had gone to the provider again.
- **Saved by routing (estimate):** the same tokens priced on the strong model, minus what they cost on the cheap one. It's an estimate because different models produce slightly different token counts.
