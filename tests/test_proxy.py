import json
import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

seen = []  # request bodies the fake provider received


def _sse(events, done=True) -> bytes:
    out = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    if done:
        out += "data: [DONE]\n\n"
    return out.encode()


def fake_upstream(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    seen.append(body)
    anthropic = "anthropic" in str(request.url)
    if body.get("stream"):
        if anthropic:
            events = [
                {"type": "message_start", "message": {"usage": {"input_tokens": 1000, "output_tokens": 1}}},
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}},
                {"type": "message_delta", "usage": {"output_tokens": 500}},
                {"type": "message_stop"},
            ]
            return httpx.Response(200, content=_sse(events, done=False),
                                  headers={"content-type": "text/event-stream"})
        events = [
            {"choices": [{"delta": {"content": "hi"}}]},
            {"choices": [], "usage": {"prompt_tokens": 1000, "completion_tokens": 500}},
        ]
        return httpx.Response(200, content=_sse(events), headers={"content-type": "text/event-stream"})
    if anthropic:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}],
                                         "usage": {"input_tokens": 1000, "output_tokens": 500}})
    return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}],
                                     "usage": {"prompt_tokens": 1000, "completion_tokens": 500}})


@pytest.fixture()
def client():
    with TestClient(app) as c:
        app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(fake_upstream))
        with db._lock:
            db._db().execute("DELETE FROM calls")
            db._db().execute("DELETE FROM cache")
            db._db().commit()
        seen.clear()
        yield c


def chat(content, **extra):
    return {"messages": [{"role": "user", "content": content}], **extra}


def test_logs_cost_and_caches(client):
    body = chat("hello", model="gpt-4o-mini", temperature=0)
    headers = {"X-Team": "search", "X-Feature": "summarize", "Authorization": "Bearer test"}

    r1 = client.post("/openai/v1/chat/completions", json=body, headers=headers)
    assert r1.status_code == 200
    assert r1.headers["x-cost-guard-cache"] == "miss"
    # 1000 * 0.15/1M + 500 * 0.60/1M = 0.00045
    assert abs(float(r1.headers["x-cost-guard-cost-usd"]) - 0.00045) < 1e-9

    r2 = client.post("/openai/v1/chat/completions", json=body, headers=headers)
    assert r2.headers["x-cost-guard-cache"] == "hit"
    assert len(seen) == 1  # second call never reached the provider

    client.post("/anthropic/v1/messages", headers={"X-Team": "support", "x-api-key": "test"},
                json=chat("hello", model="claude-haiku-4-5", max_tokens=100))

    s = client.get("/stats").json()
    assert s["totals"]["calls"] == 3
    assert s["totals"]["cache_hits"] == 1
    assert abs(s["totals"]["saved_usd"] - 0.00045) < 1e-9
    assert {t["name"] for t in s["by_team"]} == {"search", "support"}


def test_auto_routes_simple_prompt_to_cheap_model(client):
    r = client.post("/openai/v1/chat/completions", json=chat("What's the capital of France?", model="auto"))
    assert r.status_code == 200
    assert r.headers["x-cost-guard-model"] == "gpt-4o-mini"
    assert seen[-1]["model"] == "gpt-4o-mini"
    # strong would cost 1000*2.5/1M + 500*10/1M = 0.0075; cheap costs 0.00045
    s = client.get("/stats").json()["totals"]
    assert s["routed_calls"] == 1
    assert abs(s["routing_saved_usd"] - (0.0075 - 0.00045)) < 1e-9


def test_auto_routes_complex_prompt_to_strong_model(client):
    r = client.post("/openai/v1/chat/completions",
                    json=chat("Debug this stack trace and explain why it fails", model="auto"))
    assert r.headers["x-cost-guard-model"] == "gpt-4o"
    assert "keyword" in r.headers["x-cost-guard-route-reason"]

    r = client.post("/openai/v1/chat/completions", json=chat("x" * 5000, model="auto"))
    assert r.headers["x-cost-guard-model"] == "gpt-4o"
    assert r.headers["x-cost-guard-route-reason"] == "long prompt"

    r = client.post("/openai/v1/chat/completions", json=chat("hi", model="auto", tools=[{"type": "function"}]))
    assert r.headers["x-cost-guard-model"] == "gpt-4o"


def test_explicit_model_is_never_rerouted(client):
    r = client.post("/openai/v1/chat/completions", json=chat("hi", model="gpt-4o"))
    assert r.headers["x-cost-guard-model"] == "gpt-4o"
    assert seen[-1]["model"] == "gpt-4o"


def test_openai_streaming_passes_through_and_is_priced(client):
    with client.stream("POST", "/openai/v1/chat/completions",
                       json=chat("hello", model="gpt-4o-mini", stream=True),
                       headers={"X-Team": "chat"}) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())
    assert '"content": "hi"' in text and "[DONE]" in text
    assert seen[-1]["stream_options"] == {"include_usage": True}

    s = client.get("/stats").json()["totals"]
    assert s["streamed_calls"] == 1
    assert abs(s["cost_usd"] - 0.00045) < 1e-9


def test_anthropic_streaming_is_priced(client):
    with client.stream("POST", "/anthropic/v1/messages",
                       json=chat("hello", model="claude-haiku-4-5", max_tokens=100, stream=True)) as r:
        assert r.status_code == 200
        "".join(r.iter_text())
    s = client.get("/stats").json()["totals"]
    # 1000 * 1.00/1M + 500 * 5.00/1M = 0.0035
    assert abs(s["cost_usd"] - 0.0035) < 1e-9


def test_streams_are_not_cached(client):
    for _ in range(2):
        with client.stream("POST", "/openai/v1/chat/completions",
                           json=chat("hello", model="gpt-4o-mini", temperature=0, stream=True)) as r:
            "".join(r.iter_text())
    assert len(seen) == 2
