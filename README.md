# Hermes Cache-Friendly Auxiliary Routing

> A practical pattern for improving prompt cache locality in Hermes-style agents
> by routing auxiliary tasks away from the main model endpoint.

## Problem

Hermes and similar AI agents trigger many **background tasks** during normal operation:

- **title_generation** — auto-naming conversations
- **web_extract** — reading and summarizing web content
- **session_search** — searching past conversation history
- **background_review** — post-turn reflection and analysis
- **memory** operations — reading/writing persistent facts
- **compression** — summarizing long conversations

These tasks often use the **same model endpoint** as the main conversation. When the main model uses prompt caching (KV cache, llama-server slot cache, or cloud prompt cache), background requests can:

- Evict the cached KV state from the inference slot
- Fragment the prompt prefix, causing cache misses
- Trigger unnecessary re-prefills on the next user message
- Increase latency and cost for cloud API users

## Key Idea

**Route low-risk auxiliary tasks to a separate, cheaper endpoint.**

```
main_chat         → main provider      (fast, cached, high-quality)
title_generation  → auxiliary provider (cheap, separate, disposable)
web_extract       → auxiliary provider
session_search    → auxiliary provider
background_review → auxiliary provider
compression       → default provider   (quality-critical, do NOT reroute)
```

The auxiliary provider can be:

- A local LM Studio instance
- A secondary llama.cpp / Ollama endpoint
- A cheap cloud model (OpenRouter, together.ai)
- Any OpenAI-compatible API

## What This Improves

| Area | Benefit |
|------|---------|
| **Cache stability** | Main conversation maintains consistent slot cache |
| **Latency** | Fewer unexpected re-prefills on user turns |
| **Cost** | Background tasks use cheaper models |
| **Routing clarity** | Each task type has an explicit, observable target |
| **Main endpoint load** | Fewer requests competing for the main model |

## Important Distinction: Compression

**Compression should usually remain on the default/high-quality routing.**

Compression rewrites the entire conversation context. Cache continuity is already broken by definition during compression. What matters is **summary quality** — a poor summary degrades all subsequent turns.

Do not route compression to a cheap auxiliary model. Use the best model available.

## Configuration

Add an `auxiliary` section to your Hermes `config.yaml`:

```yaml
auxiliary:
  title_generation:
    provider: aux-model
    model: small-or-cheap-model
    fallback_chain:
      - provider: default-cloud-provider
        model: fallback-model

  web_extract:
    provider: aux-model
    model: small-or-cheap-model

  session_search:
    provider: aux-model
    model: small-or-cheap-model

  background_review:
    provider: aux-model
    model: small-or-cheap-model

  compression:
    provider: auto
    # compression stays on default routing
```

See [`docs/config-examples.md`](docs/config-examples.md) for detailed examples with local LM Studio, remote LAN, cloud providers, and hybrid setups.

## Case Study: 200K Context Local Model

A real-world deployment with the following setup:

| Component | Detail |
|-----------|--------|
| **Main model** | Qwen3.6 27B GGUF via llama-server |
| **Context** | 200,000 tokens |
| **Cache** | `--cache-prompt --cache-reuse 256` |
| **Slot** | Single slot (`--parallel 1`) |
| **Auxiliary model** | Qwen3.5 35B A3B via LM Studio (separate machine) |

**Configuration:**

```yaml
auxiliary:
  title_generation:
    provider: mac-local
    model: qwen/qwen3.5-35b-a3b
  web_extract:
    provider: mac-local
    model: qwen/qwen3.5-35b-a3b
  session_search:
    provider: mac-local
    model: qwen/qwen3.5-35b-a3b
  background_review:
    provider: mac-local
    model: qwen/qwen3.5-35b-a3b
  compression:
    provider: auto
```

**Results:**

- Main conversation cache hit rate: **~100%** on consecutive stable turns
- Memory updates cause one-time partial prefill (expected — system prompt prefix changes)
- Cache recovers on the next turn
- Background tasks no longer appear in the main endpoint's request log

## Cache Behavior Principles

See [`docs/cache-behavior.md`](docs/cache-behavior.md) for the full set of principles derived from testing. Key takeaways:

1. **Identical prompts should cache-hit** — if they don't, something is modifying the request.
2. **Stable prefix improves hit rate** — keep the system prompt consistent.
3. **Memory snapshot changes trigger one-time partial prefill** — this is normal, not a bug.
4. **Tool calls temporarily reduce hit rate** — expected and acceptable.
5. **Background tasks should avoid the main endpoint** — route them away.

## Fallback Strategy

The auxiliary provider may be unavailable. A good fallback strategy:

- Falls back through the configured `fallback_chain`
- Logs the fallback event for observability
- Does **not** hardcode a specific main model endpoint as fallback
- Falling back to the main provider is acceptable but should be observable

## Troubleshooting

See [`docs/troubleshooting.md`](docs/troubleshooting.md) for diagnostic workflows, including:

- Proxy audit setup to inspect real requests
- Prefix hash comparison to detect system prompt changes
- Timeline analysis to identify cache-breaking events

## Applicability

This pattern applies to any agent that:

- Uses prompt caching (llama.cpp slot cache, KV cache, cloud prompt caching)
- Has a stable system prompt prefix
- Triggers background tasks during or between conversation turns
- Wants to reduce latency and cost on the main model endpoint

Compatible with:

- **llama.cpp** / llama-server
- **LM Studio**
- **Ollama** and OpenAI-compatible endpoints
- **OpenRouter**, **Together AI**, and other cloud providers
- **OpenAI** / **Anthropic** / **Gemini** prompt caching
- Any **Hermes**-compatible agent

## Repository Structure

```
.
├── README.md
├── LICENSE
├── .gitignore
├── docs/
│   ├── background.md          # Prompt caching theory & why routing matters
│   ├── config-examples.md     # Provider configuration examples
│   ├── cache-behavior.md      # Principles from real-world testing
│   └── troubleshooting.md     # Diagnostic workflows
└── examples/
    ├── config.yaml             # Full annotated config example
    ├── background_review_patch.py  # Illustrative patch for Hermes
    ├── proxy_audit.py          # Lightweight request audit proxy
    └── request_timeline_example.md # Anonymized timeline analysis
```

## Getting Started

1. Identify which auxiliary tasks your agent runs (check agent logs)
2. Set up an auxiliary provider (local LM Studio, secondary endpoint, or cheap cloud model)
3. Add the `auxiliary` section to your `config.yaml`
4. Verify routing by checking agent logs for `provider=` lines
5. (Optional) Run `proxy_audit.py` to confirm background tasks are not hitting the main endpoint

## License

MIT — see [LICENSE](LICENSE)
