# Background: Prompt Caching and Auxiliary Task Pollution

## How prompt caching works

LLM inference typically processes the full context on every request. To avoid recomputing the same prefix repeatedly, many serving systems implement **prefix-based caching**:

- **Cloud prompt caching** (OpenAI, Anthropic, Gemini): The API caches KV states for repeated prompt prefixes and skips recomputation on subsequent requests with the same prefix.
- **llama-server slot cache**: llama.cpp's server (`llama-server`) maintains per-slot KV caches. When `--cache-prompt` is enabled, the server saves and restores prompt KV state across requests, avoiding re-processing identical prefixes.
- **KV cache reuse**: The server can reuse previously computed KV tensors when the new prompt shares a common prefix with a cached state.

The key enabler: a **stable system prompt prefix** that does not change between turns.

## Why background requests can hurt cache locality

Hermes and similar agents trigger several types of **auxiliary tasks** during or between conversation turns:

- `title_generation` — auto-generating conversation titles
- `web_extract` — reading web page content
- `session_search` — searching past conversation history
- `background_review` — post-turn analysis and reflection
- `memory` operations — reading/writing persistent memory
- `compression` — summarizing long conversations

These tasks often use the **same model endpoint** as the main conversation. This causes problems:

### 1. Slot eviction (llama-server)

With `--parallel 1` (single slot), a background request from `background_review` may:
- Evict the main conversation's KV cache from the slot
- Force a complete re-prefill on the next user message
- Wipe out the benefit of `--cache-prompt`

Even with `--parallel 2`, background requests compete for VRAM and may fragment the slot allocation.

### 2. Prefix fragmentation (cloud APIs)

Cloud prompt caching relies on exact prefix matching. If `background_review` sends a different system prompt or no system prompt at all, the subsequent main request may:
- Fail the prefix match due to a changed system prompt
- Incur full prompt processing cost and latency
- Burn through cached tokens budget

### 3. Dynamic memory blocks

Persistent memory (stored facts, preferences, environment notes) is injected into the system prompt. When memory is updated during a conversation:
- The system prompt changes
- The old prefix-based cache becomes invalid
- A one-time partial re-prefill is unavoidable

**This is normal, expected behavior** — not a bug. The new prefix warms up on the next turn.

## The auxiliary routing pattern

The solution is simple: **route auxiliary tasks to a separate provider**.

```
main_chat        → main provider (fast, cached, expensive)
title_generation → auxiliary provider (cheap, separate, disposable)
web_extract      → auxiliary provider
session_search   → auxiliary provider
background_review→ auxiliary provider
compression      → default / high-quality provider (do NOT route to auxiliary)
```

### Why compression is special

Compression rewrites or summarizes the entire conversation context. Cache continuity is already broken by definition during compression. What matters is **summary quality** — a poor summary degrades all subsequent turns. Compression should use the best available model, not a cheap auxiliary one.

### Fallback strategy

The auxiliary provider may be unavailable (offline, overloaded, out of credits). A good implementation:
- Falls back gracefully to the default provider chain
- Logs the fallback event for observability
- Does NOT hardcode a specific fallback endpoint

Fallback to the main provider is acceptable, but should be observable so you can detect when the cache is being polluted again.

## Real-world impact

In our testing with a llama-server endpoint (200K context, single slot, `--cache-prompt`):

| Configuration | Cache hit rate (stable turns) | Notes |
|---|---|---|
| All tasks on main endpoint | 85–95% | Background tasks occasionally evict slot |
| Auxiliary tasks routed to secondary | 99–100% | Only memory updates cause partial prefill |

The improvement is most noticeable on long-running sessions where background tasks fire frequently.
