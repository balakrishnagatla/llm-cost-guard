# LLM Cost Guard

**A drop-in gateway that shows what every AI call costs, and cuts that cost automatically.**

Companies are putting large language models (LLMs) into real products. The bills grow fast, and almost nobody can answer simple questions like *"which team spent this?"* or *"did that feature need the expensive model?"* LLM Cost Guard sits between your apps and the AI providers, measures every call, and applies three proven savings levers: caching, model routing and budgets.

```
your app ──► LLM Cost Guard ──► OpenAI / Anthropic / Groq / Gemini / Ollama
                 │
                 ├─ measures tokens, cost and latency per team and feature
                 ├─ answers repeat questions from cache ($0)
                 ├─ sends simple prompts to a cheaper model
                 └─ stops a team at its daily budget
```

## At a glance

| | |
|---|---|
| **Problem** | AI spend is growing fast with no visibility or control per team or feature |
| **Solution** | A small proxy: change one URL in your app, get cost tracking and savings |
| **Savings levers** | Response cache, automatic model routing, per-team daily budgets |
| **Security** | Per-team keys, dashboard login, cache isolation, hardened container |
| **Works with** | Any OpenAI-compatible API (OpenAI, Groq, Gemini, OpenRouter, Ollama) and Anthropic |
| **Stack** | Python, FastAPI, SQLite, Docker, GitHub Actions |

## Read next

1. [The Problem](The-Problem.md): why AI costs get out of hand, and why the usual stopgaps fall short
2. [How It Works](How-It-Works.md): architecture and request flow
3. [Results and Findings](Results.md): what a real test run showed
4. [Security](Security.md): how the gateway protects keys, data and budgets
5. [Getting Started](Getting-Started.md): run it in five minutes with a free API
6. [Project History](Project-History.md): what was built, release by release
7. [Roadmap](Roadmap.md): what comes next
