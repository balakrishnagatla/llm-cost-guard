# Getting Started

You'll need Docker and an API key. A free Groq key works: create one at console.groq.com/keys.

## 1. Get the code and configure

```bash
git clone https://github.com/balakrishnagatla/llm-cost-guard.git
cd llm-cost-guard
cp .env.example .env
```

Edit `.env`:

```
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_API_KEY=your_groq_key
```

Set the Groq models in `routing.json`:

```json
"openai": { "cheap": "openai/gpt-oss-20b", "strong": "openai/gpt-oss-120b" }
```

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

If the dashboard reports "unable to open database file" after upgrading from v0.2, run `chmod 777 data` once.
