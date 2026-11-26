"""End-to-end checks against a real provider through a running gateway.

Usage: start the gateway on localhost:8080, then run `python scripts/live_smoke.py`.
Prints a summary to stdout and to the GitHub Actions job summary when available.
"""
import json
import os
import sys
import urllib.request

BASE = os.getenv("GATEWAY_URL", "http://localhost:8080")
if not BASE.startswith(("http://", "https://")):
    sys.exit("GATEWAY_URL must be an http(s) URL")


def call(prompt: str, feature: str) -> tuple[dict, dict]:
    body = json.dumps({"model": "auto", "temperature": 0,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(  # noqa: S310 (scheme checked above)
        f"{BASE}/openai/v1/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Team": "ci", "X-Feature": feature})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 (scheme checked above)
        return dict(resp.headers), json.loads(resp.read())


def main() -> int:
    failures = []
    h1, b1 = call("Say hello in five words", "greeting")
    h2, _ = call("Say hello in five words", "greeting")
    h3, _ = call("Analyze the trade-offs of caching LLM responses step by step, briefly", "analysis")

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
        if not ok:
            failures.append(name)

    answer = str(b1.get("choices", [{}])[0].get("message", {}).get("content"))
    m1, m3 = h1.get("x-cost-guard-model", ""), h3.get("x-cost-guard-model", "")
    check("real answer", bool(b1.get("choices")), answer[:60])
    check("simple prompt -> cheap model", m1.endswith("20b"), m1)
    check("repeat -> cache hit", h2.get("x-cost-guard-cache") == "hit", h2.get("x-cost-guard-cache", ""))
    check("complex prompt -> strong model", m3.endswith("120b"), m3)

    with urllib.request.urlopen(f"{BASE}/stats", timeout=10) as resp:  # noqa: S310
        t = json.loads(resp.read())["totals"]
    check("calls logged", t["calls"] == 3, str(t["calls"]))
    summary = (f"Spend ${t['cost_usd']:.6f} · saved by cache ${t['saved_usd']:.6f} · "
               f"saved by routing ${t['routing_saved_usd']:.6f} · output tokens {t['output_tokens']} "
               f"(reasoning {t['reasoning_tokens']})")
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            status = "All checks passed" if not failures else "Failed: " + ", ".join(failures)
            f.write(f"### Live smoke test\n\n{status}\n\n{summary}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
