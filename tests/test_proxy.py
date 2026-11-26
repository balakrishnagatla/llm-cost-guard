import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

import httpx
from fastapi.testclient import TestClient

from app.main import app

calls = {"n": 0}


def fake_upstream(request: httpx.Request) -> httpx.Response:
    calls["n"] += 1
    if "anthropic" in str(request.url):
        return httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}],
                                         "usage": {"input_tokens": 1000, "output_tokens": 500}})
    return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}],
                                     "usage": {"prompt_tokens": 1000, "completion_tokens": 500}})


def test_logs_cost_and_caches():
    with TestClient(app) as client:
        app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(fake_upstream))
        body = {"model": "gpt-4o-mini", "temperature": 0, "messages": [{"role": "user", "content": "hello"}]}
        headers = {"X-Team": "search", "X-Feature": "summarize", "Authorization": "Bearer test"}

        r1 = client.post("/openai/v1/chat/completions", json=body, headers=headers)
        assert r1.status_code == 200
        assert r1.headers["x-cost-guard-cache"] == "miss"
        # 1000 * 0.15/1M + 500 * 0.60/1M = 0.00045
        assert abs(float(r1.headers["x-cost-guard-cost-usd"]) - 0.00045) < 1e-9

        r2 = client.post("/openai/v1/chat/completions", json=body, headers=headers)
        assert r2.headers["x-cost-guard-cache"] == "hit"
        assert calls["n"] == 1  # second call never reached the provider

        client.post("/anthropic/v1/messages", headers={"X-Team": "support", "x-api-key": "test"},
                    json={"model": "claude-haiku-4-5", "max_tokens": 100,
                          "messages": [{"role": "user", "content": "hello"}]})

        s = client.get("/stats").json()
        assert s["totals"]["calls"] == 3
        assert s["totals"]["cache_hits"] == 1
        assert abs(s["totals"]["saved_usd"] - 0.00045) < 1e-9
        assert {t["name"] for t in s["by_team"]} == {"search", "support"}


def test_rejects_streaming():
    with TestClient(app) as client:
        r = client.post("/openai/v1/chat/completions", json={"model": "gpt-4o", "stream": True})
        assert r.status_code == 400
