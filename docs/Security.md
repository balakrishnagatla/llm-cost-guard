# Security

The gateway holds provider API keys and sees every prompt, so it's treated as sensitive infrastructure.

## Threats and protections

| Threat | Protection |
|---|---|
| Someone uses the gateway to spend your API key | Per-team proxy keys (`COST_GUARD_KEYS`), compared in constant time |
| A team bills its usage to another team | Team is taken from the key, never from a header |
| A leaked key or runaway loop runs up a huge bill | Daily budgets per team (`BUDGETS`), HTTP 429 when reached |
| One user receives another user's cached answer | Cache entries are scoped to a salted PBKDF2 fingerprint of the upstream API key |
| A copied database reveals API keys | The cache never stores keys; the fingerprint uses PBKDF2-HMAC-SHA256 with a random per-install salt (`data/fingerprint.salt`, mode 0600), so it can't be used to test key guesses offline |
| Script injection through team/feature names (XSS) | Names are validated before storage and escaped in the dashboard |
| Anyone reads spend data | Dashboard and `/stats` require a password (`DASHBOARD_PASSWORD`) |
| Huge requests exhaust memory | Bodies over `MAX_BODY_BYTES` are refused (413) |
| Clickjacking, content sniffing | CSP with `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff` |
| Accidental exposure on a network | Docker binds to `127.0.0.1` only; API docs endpoints are disabled |
| Container breakout impact | Non-root user, all Linux capabilities dropped, `no-new-privileges` |
| Backup provider keys leaking to callers | Failover keys are read server-side from the environment and never returned |
| Spend data leaking through monitoring | `/calls` and `/stats` need the dashboard password; `/metrics` can require `METRICS_TOKEN`; Prometheus, Grafana and Jaeger bind to localhost only; prompts and answers are never put in traces or metrics |

## Repository protections

- `main` is protected: changes go through pull requests that must pass all checks; force pushes and deletion are blocked.
- Every pull request runs the tests, `pip-audit` (known vulnerable dependencies), `bandit` (static security scan) and a Docker build.
- Dependabot keeps Python packages, the Docker base image and GitHub Actions up to date.
- Secret scanning with push protection blocks commits that contain API keys.
- Vulnerabilities can be reported privately; see [SECURITY.md](../SECURITY.md).
- The live smoke test uses a Groq key stored as a secret in the `live` **GitHub environment**. Environment secrets are encrypted, masked in logs and only available to jobs that name the environment; the workflow never runs on pull requests, so untrusted code can't read the key.
- Lint (`ruff`, including security rules), type checks (`mypy`) and an 85% coverage floor run on every pull request.

## Running it safely

- Keep it on localhost for development.
- Before exposing it to a network: set `COST_GUARD_KEYS` and `DASHBOARD_PASSWORD`, and put it behind HTTPS.
- Treat the `data/` folder like logs: it contains cached responses.
- Never commit `.env`.
