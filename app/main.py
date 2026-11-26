"""LLM Cost Guard: a proxy that logs cost per team/feature, caches repeat calls,
and routes simple prompts to cheaper models.

Point your app at this proxy instead of the provider:
  OpenAI-compatible:  POST http://localhost:8080/openai/v1/chat/completions
  Anthropic:          POST http://localhost:8080/anthropic/v1/messages
Tag calls with headers:  X-Team: search   X-Feature: summarize
Set "model": "auto" to let the proxy pick a cheap or strong model.
"""
import codecs
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import logging

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from . import db
from .pricing import cost_usd, is_priced
from .router import route
from .security import (clean_label, credential_fingerprint, parse_budgets, proxy_keys,
                       require_dashboard_login, resolve_team)

log = logging.getLogger("cost_guard")

OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
ANTHROPIC_BASE = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
# deterministic = cache only temperature 0 calls; all = cache everything; off = no cache
CACHE_MODE = os.getenv("CACHE_MODE", "deterministic").lower()
CACHE_TTL_SECONDS = float(os.getenv("CACHE_TTL_SECONDS", "86400"))
UPSTREAM_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "120"))
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(1_000_000)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # Fail fast on bad config instead of at the first request.
    keys = proxy_keys()
    app.state.budgets = parse_budgets(os.getenv("BUDGETS", ""))
    if not keys:
        log.warning("COST_GUARD_KEYS is not set: proxy is in open dev mode. Keep it on localhost.")
    if not os.getenv("DASHBOARD_PASSWORD"):
        log.warning("DASHBOARD_PASSWORD is not set: dashboard and /stats are not password protected.")
    app.state.client = httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT)
    yield
    await app.state.client.aclose()


app = FastAPI(title="LLM Cost Guard", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
    return response


# ---------- provider-specific usage parsing ----------

def _openai_usage(data: dict):
    u = data.get("usage") or {}
    return int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))


def _anthropic_usage(data: dict):
    u = data.get("usage") or {}
    return int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))


def _openai_stream_event(event: dict, usage: dict) -> None:
    # OpenAI sends usage in the last chunk when stream_options.include_usage is set;
    # Groq puts it under x_groq.usage.
    u = event.get("usage") or (event.get("x_groq") or {}).get("usage")
    if u:
        usage["in"] = int(u.get("prompt_tokens", usage["in"]))
        usage["out"] = int(u.get("completion_tokens", usage["out"]))


def _anthropic_stream_event(event: dict, usage: dict) -> None:
    if event.get("type") == "message_start":
        u = (event.get("message") or {}).get("usage") or {}
        usage["in"] = int(u.get("input_tokens", 0))
        usage["out"] = int(u.get("output_tokens", 0))
    elif event.get("type") == "message_delta":
        u = event.get("usage") or {}
        usage["out"] = int(u.get("output_tokens", usage["out"]))  # cumulative


PROVIDERS = {
    "openai": {"usage": _openai_usage, "stream_event": _openai_stream_event},
    "anthropic": {"usage": _anthropic_usage, "stream_event": _anthropic_stream_event},
}


# ---------- helpers ----------

def _cacheable(body: dict) -> bool:
    if body.get("stream") or CACHE_MODE == "off":
        return False
    if CACHE_MODE == "all":
        return True
    return body.get("temperature") == 0


def _costs(model: str, baseline: str | None, in_t: int, out_t: int):
    cost = cost_usd(model, in_t, out_t)
    routing_saved = 0.0
    if baseline and baseline != model:
        # Estimate: what the same tokens would have cost on the strong model.
        routing_saved = max(cost_usd(baseline, in_t, out_t) - cost, 0.0)
    return cost, routing_saved


def _guard_headers(model: str, reason: str | None, cache: str, cost: float | None = None) -> dict:
    h = {"x-cost-guard-model": model, "x-cost-guard-cache": cache}
    if reason:
        h["x-cost-guard-route-reason"] = reason
    if cost is not None:
        h["x-cost-guard-cost-usd"] = f"{cost:.6f}"
    return h


# ---------- core proxy ----------

async def _proxy(request: Request, provider: str, url: str, headers: dict) -> Response:
    team = resolve_team(request)  # 401 if a key is required and missing

    if int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
        raise HTTPException(413, "Request body too large")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(413, "Request body too large")
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Request body must be JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "Request body must be a JSON object")

    budget = request.app.state.budgets.get(team)
    if budget is not None:
        spent = db.spent_today(team)
        if spent >= budget:
            raise HTTPException(429, f"Daily budget for team '{team}' reached (${spent:.4f} of ${budget:.2f}). "
                                     "Resets at 00:00 UTC.")

    requested = body.get("model", "unknown")
    try:
        model, baseline, reason = route(provider, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    body["model"] = model

    meta = dict(
        provider=provider, model=model, requested_model=requested,
        team=team,
        feature=clean_label(request.headers.get("x-feature")),
        priced=int(is_priced(model)),
    )
    funcs = PROVIDERS[provider]
    start = time.perf_counter()

    if body.get("stream"):
        return await _proxy_stream(request, provider, url, headers, body, meta, baseline, reason, start)

    # Cache entries are scoped to the upstream credential so answers never leak across API keys.
    key = hashlib.sha256(
        (provider + credential_fingerprint(headers) + json.dumps(body, sort_keys=True)).encode()).hexdigest()
    if _cacheable(body):
        cached = db.get_cached(key, CACHE_TTL_SECONDS)
        if cached is not None:
            in_t, out_t = funcs["usage"](cached)
            db.log_call(**meta, input_tokens=in_t, output_tokens=out_t, cost_usd=0.0,
                        saved_usd=cost_usd(model, in_t, out_t), routing_saved_usd=0.0,
                        latency_ms=(time.perf_counter() - start) * 1000, cache_hit=1, status=200)
            return JSONResponse(cached, headers=_guard_headers(model, reason, "hit", 0.0))

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
    cost = routing_saved = 0.0
    if resp.status_code == 200:
        in_t, out_t = funcs["usage"](data)
        cost, routing_saved = _costs(model, baseline, in_t, out_t)
        if _cacheable(body):
            db.put_cache(key, data)

    db.log_call(**meta, input_tokens=in_t, output_tokens=out_t, cost_usd=cost, saved_usd=0.0,
                routing_saved_usd=routing_saved, latency_ms=latency, cache_hit=0, status=resp.status_code)
    return JSONResponse(data, status_code=resp.status_code,
                        headers=_guard_headers(model, reason, "miss", cost))


async def _proxy_stream(request, provider, url, headers, body, meta, baseline, reason, start) -> Response:
    if provider == "openai":
        # Ask for token usage in the final chunk so we can price the call.
        body.setdefault("stream_options", {"include_usage": True})

    client: httpx.AsyncClient = request.app.state.client
    try:
        resp = await client.send(client.build_request("POST", url, json=body, headers=headers), stream=True)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Upstream request failed: {e}")

    if resp.status_code != 200:
        content = await resp.aread()
        await resp.aclose()
        db.log_call(**meta, input_tokens=0, output_tokens=0, cost_usd=0.0, saved_usd=0.0,
                    routing_saved_usd=0.0, latency_ms=(time.perf_counter() - start) * 1000,
                    cache_hit=0, status=resp.status_code, streamed=1)
        return Response(content, status_code=resp.status_code,
                        media_type=resp.headers.get("content-type", "application/json"))

    on_event = PROVIDERS[provider]["stream_event"]
    usage = {"in": 0, "out": 0}

    async def relay():
        decoder = codecs.getincrementaldecoder("utf-8")()
        buf = ""
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk  # pass bytes through untouched
                buf += decoder.decode(chunk)
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if payload and payload != "[DONE]":
                            try:
                                on_event(json.loads(payload), usage)
                            except (json.JSONDecodeError, AttributeError):
                                pass
        finally:
            await resp.aclose()
            cost, routing_saved = _costs(meta["model"], baseline, usage["in"], usage["out"])
            db.log_call(**meta, input_tokens=usage["in"], output_tokens=usage["out"], cost_usd=cost,
                        saved_usd=0.0, routing_saved_usd=routing_saved,
                        latency_ms=(time.perf_counter() - start) * 1000,
                        cache_hit=0, status=200, streamed=1)

    return StreamingResponse(relay(), media_type="text/event-stream",
                             headers=_guard_headers(meta["model"], reason, "bypass"))


# ---------- routes ----------

@app.post("/openai/v1/chat/completions")
async def openai_chat(request: Request):
    auth = request.headers.get("authorization") or f"Bearer {os.getenv('OPENAI_API_KEY', '')}"
    return await _proxy(request, "openai", f"{OPENAI_BASE}/chat/completions", {"Authorization": auth})


@app.post("/anthropic/v1/messages")
async def anthropic_messages(request: Request):
    headers = {
        "x-api-key": request.headers.get("x-api-key") or os.getenv("ANTHROPIC_API_KEY", ""),
        "anthropic-version": request.headers.get("anthropic-version", "2023-06-01"),
    }
    return await _proxy(request, "anthropic", f"{ANTHROPIC_BASE}/v1/messages", headers)


@app.get("/stats", dependencies=[Depends(require_dashboard_login)])
def get_stats(request: Request):
    s = db.stats()
    spent = db.spent_today_by_team()
    s["budgets"] = [
        {"team": t, "budget_usd": b, "spent_today_usd": round(spent.get(t, 0.0), 6)}
        for t, b in sorted(request.app.state.budgets.items())
    ]
    return s


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_dashboard_login)])
@app.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(require_dashboard_login)])
def dashboard():
    return (Path(__file__).parent / "dashboard.html").read_text()
