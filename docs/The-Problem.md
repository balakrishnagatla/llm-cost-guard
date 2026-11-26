# The Problem

## AI costs are a new kind of bill

Traditional cloud costs scale with servers. LLM costs scale with **tokens**: every word sent to a model and every word it writes back. That makes the bill:

- **Invisible until it arrives.** A single shared API key hides which team, feature or customer caused the spend.
- **Easy to inflate by accident.** A chatbot that sends a long system prompt with every message, a retry loop, or a prompt sent to a top-tier model when a small one would do, all multiply costs quietly.
- **Growing faster than usage.** Newer "reasoning" models think before they answer, and those hidden thinking tokens are billed as output. In our own test, they made up most of the cost of a call (see [Results](Results.md)).

Cheaper prices per token don't fix this. As AI gets cheaper per call, teams make far more calls, and total spend keeps rising.

## The stopgaps teams use today

| Stopgap | What it does | Why it falls short |
|---|---|---|
| **Reading the provider invoice** | Monthly total from OpenAI, Anthropic and others | Too late and too coarse: one number per key, no team or feature breakdown |
| **One API key per team** | Splits spend by key | Key sprawl, keys leak, still no per-feature view, no savings |
| **Provider rate limits / hard caps** | Stops spend at a limit | Blunt: the whole product stops, not just the team that overspent |
| **"Use the cheap model" guidelines** | Asks developers to pick smaller models | Depends on every developer remembering; no way to measure if it happened |
| **Spreadsheets of usage exports** | Manual monthly analysis | Slow, error-prone, and nobody acts on it in time |

These all treat the symptom after the fact. None of them **measures at the moment of the call** or **acts automatically**.

## What a real solution needs

1. **Visibility at the call level:** cost per team, per feature and per model, in real time.
2. **Automatic savings:** don't pay twice for the same answer; don't use a large model for a small question.
3. **Guardrails:** a runaway loop or leaked key should hit a budget, not an unlimited bill.
4. **No rewrite:** teams should adopt it by changing one URL, not their code.
5. **Safe by default:** the component holding the provider keys has to be secure.

That's what LLM Cost Guard does. Next: [How It Works](How-It-Works.md).
