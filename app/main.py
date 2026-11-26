"""LLM Cost Guard: a proxy that logs cost per team/feature and caches repeat calls.

Point your app at this proxy instead of the provider:
  OpenAI-compatible:  POST http://localhost:8080/openai/v1/chat/completions
  Anthropic:          POST http://localhost:8080/anthropic/v1/messages
Tag calls with headers:  X-Team: search   X-Feature: summarize
"""
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import db
from .pricing import cost_usd, is_priced

OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
ANTHROPIC_BASE = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
# deterministic = cache only temperature 0 calls; all = cache everything; off = no cache
CACHE_MODE = os.getenv("CACHE_MODE", "deterministic").lower()
CACHE_TTL_SECONDS = float(os.getenv("CACHE_TTL_SECONDS", "86400"))
UPSTREAM_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "120"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    app.state.client = httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT)
    yield
    await app.state.client.aclose()


app = FastAPI(title="LLM Cost Guard", lifespan=lifespan)


def _cacheable(body: dict) -> bool:
    if CACHE_MODE == "off":
        return False
    if CACHE_MODE == "all":
        return True
    return body.get("temperature") == 0


def _openai_usage(data: dict):
    u = data.get("usage") or {}
    return int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))


def _anthropic_usage(data: dict):
    u = data.get("usage") or {}
    return int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))


async def _proxy(request: Request, provider: str, url: str, headers: dict, usage_of) -> JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(400, "Request body must be JSON")
    if body.get("stream"):
        raise HTTPException(400, "Streaming isn't supported yet (planned for week 2)")

    team = request.headers.get("x-team", "unknown")
    feature = request.headers.get("x-feature", "unknown")
    model = body.get("model", "unknown")
    meta = dict(provider=provider, model=model, team=team, feature=feature, priced=int(is_priced(model)))
    key = hashlib.sha256((provider + json.dumps(body, sort_keys=True)).encode()).hexdigest()
    start = time.perf_counter()

    if _cacheable(body):
        cached = db.get_cached(key, CACHE_TTL_SECONDS)
        if cached is not None:
            in_t, out_t = usage_of(cached)
            saved = cost_usd(model, in_t, out_t)
            db.log_call(**meta, input_tokens=in_t, output_tokens=out_t, cost_usd=0.0, saved_usd=saved,
                        latency_ms=(time.perf_counter() - start) * 1000, cache_hit=1, status=200)
            return JSONResponse(cached, headers={"x-cost-guard-cache": "hit", "x-cost-guard-cost-usd": "0"})

    try:
        resp = await request.app.state.client.post(url, json=body, headers=headers)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Upstream request failed: {e}")
    latency = (time.perf_counter() - start) * 1000
    try:
        data = resp.json()
    except ValueError:
        data = {"error": resp.text}

    in_t = out_t = 0
    cost = 0.0
    if resp.status_code == 200:
        in_t, out_t = usage_of(data)
        cost = cost_usd(model, in_t, out_t)
        if _cacheable(body):
            db.put_cache(key, data)

    db.log_call(**meta, input_tokens=in_t, output_tokens=out_t, cost_usd=cost, saved_usd=0.0,
                latency_ms=latency, cache_hit=0, status=resp.status_code)
    return JSONResponse(data, status_code=resp.status_code,
                        headers={"x-cost-guard-cache": "miss", "x-cost-guard-cost-usd": f"{cost:.6f}"})


@app.post("/openai/v1/chat/completions")
async def openai_chat(request: Request):
    auth = request.headers.get("authorization") or f"Bearer {os.getenv('OPENAI_API_KEY', '')}"
    return await _proxy(request, "openai", f"{OPENAI_BASE}/chat/completions",
                        {"Authorization": auth}, _openai_usage)


@app.post("/anthropic/v1/messages")
async def anthropic_messages(request: Request):
    headers = {
        "x-api-key": request.headers.get("x-api-key") or os.getenv("ANTHROPIC_API_KEY", ""),
        "anthropic-version": request.headers.get("anthropic-version", "2023-06-01"),
    }
    return await _proxy(request, "anthropic", f"{ANTHROPIC_BASE}/v1/messages", headers, _anthropic_usage)


@app.get("/stats")
def get_stats():
    return db.stats()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return (Path(__file__).parent / "dashboard.html").read_text()
