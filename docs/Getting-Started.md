# Getting Started

You'll need Docker and an API key. A free Groq key works: create one at console.groq.com/keys.

## 1. Get the code and configure

```bash
git clone https://github.com/balakrishnagatla/llm-cost-guard.git
cd llm-cost-guard
cp .env.example .env
```

Edit `.env` and add your key:

```
OPENAI_API_KEY=your_groq_key
```

The defaults already point at Groq (`OPENAI_BASE_URL`) and its free models (`openai/gpt-oss-20b` cheap, `openai/gpt-oss-120b` strong in `routing.json`). For OpenAI or another provider, change `OPENAI_BASE_URL` and the model IDs.

## 2. Start it

```bash
docker compose up -d --build
```

Open http://localhost:8080 for the dashboard.

## 3. Send a call

```bash
curl http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" -H "X-Team: demo" -H "X-Feature: greeting" \
  -d '{"model":"auto","temperature":0,"messages":[{"role":"user","content":"Say hello"}]}' -i
```

Look for these response headers:

```
x-cost-guard-model: openai/gpt-oss-20b
x-cost-guard-cache: miss
x-cost-guard-cost-usd: 0.000074
```

Send it again and `x-cost-guard-cache` becomes `hit`.

## 4. Lock it down (before sharing it)

```bash
# Generate a key per team
python3 -c "import secrets; print('k_' + secrets.token_urlsafe(24))"
```

```
COST_GUARD_KEYS=search:k_...,support:k_...
DASHBOARD_PASSWORD=choose-a-strong-password
BUDGETS=search:5,support:2.50
```

Callers then send `X-Cost-Guard-Key` instead of `X-Team`.

## Updating

```bash
cd llm-cost-guard && git pull && docker compose up -d --build
```

Since v0.4, data is kept in a Docker named volume (`costguard-data`), so there are no folder permission issues on Linux. Data in the old `./data` folder isn't carried over.

## 5. Optional: failover

Add a backup provider so calls keep working when Groq rate-limits you. Get a free Gemini key at aistudio.google.com, set `GEMINI_API_KEY` in `.env`, and copy the `_fallbacks_example` block in `routing.json` into `fallbacks`.
