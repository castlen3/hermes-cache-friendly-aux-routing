# Cache Behavior: Principles from Testing

These principles were derived from testing a 200K context llama-server endpoint (TurboQuant fork, turbo4 K cache, q8_0 V cache) with `--cache-prompt --cache-reuse 256`.

They apply to any prefix-based prompt caching system (llama.cpp, Ollama, LM Studio, OpenAI prompt caching, Anthropic prompt caching).

## Principle 1: Identical prompts should cache-hit

When the exact same prompt is sent twice, the second request should benefit from the cache.

**Test**: Send `{"messages": [{"role": "user", "content": "Say one word: yes"}]}` twice with identical system prompt.

**Expected**: Second request should have significantly lower `prompt_ms` (or higher `prompt_tokens_per_second`).

**Observed**: `prompt_ms` dropped from ~529ms to ~124ms on the second call. Cache working correctly.

## Principle 2: Stable prefix improves hit rate

The system prompt prefix is the primary cache key. If it stays byte-identical across turns, cache hit rate approaches 100%.

**What changes the prefix:**
- Memory updates (new facts added to system prompt MEMORY section)
- Tool definition changes
- System prompt template changes
- Model switching

**What does NOT change the prefix:**
- Conversation history growth (appended to the prompt, not prepended)
- User message content
- Assistant response content

## Principle 3: Memory snapshot changes trigger one-time partial prefill

When persistent memory is updated during a conversation (e.g., saving a new fact), the system prompt changes. The old KV cache becomes invalid for the new prefix.

**What happens:**
- Next main conversation turn: partial cache hit (~85–95%)
- The unchanged portion of the prefix is still cached
- Only the changed MEMORY block and subsequent tokens need re-processing
- The turn after that: cache recovers to ~100%

**This is normal, not a bug.** It is inherent to prefix-based caching when the prefix changes.

**Mitigation**: Batch memory updates together when possible. Consider deferring non-critical memory writes.

## Principle 4: Tool calls introduce new prompt regions

When the agent uses tools (terminal, web search, file operations), the tool call and tool result are appended to the conversation history. These new regions are not in the cached prefix.

**Impact**: Cache hit rate drops temporarily during tool-use turns but recovers immediately after.

**This is expected and acceptable.** Tool calls are necessary for agent operation.

## Principle 5: Background tasks should avoid the main endpoint

Background tasks like `title_generation`, `web_extract`, `session_search`, and `background_review` often send different prompts than the main conversation. They may:

- Use shorter or no system prompt
- Process completely different content
- Arrive concurrently with main conversation requests

Routing them to a separate provider prevents slot contention and prefix fragmentation.

## Principle 6: Compression is special

Compression intentionally rewrites the conversation context to fit within the token budget. Cache continuity is irrelevant during compression — the output is a new, shorter conversation.

**Recommendation**: Compression should use the default/high-quality provider chain. Do not route it to a cheap auxiliary model — the summary quality affects all subsequent turns.

## Principle 7: Fallback should be observable, not hardcoded

If the auxiliary provider is unavailable, falling back to the main provider is acceptable. But the fallback should:
- Be logged explicitly
- Not hardcode a specific main model endpoint
- Follow the existing provider fallback chain

This way you can detect when auxiliary routing has failed and take corrective action.

## Quick reference: interpreting cache metrics

| Metric | Good | Warning |
|--------|------|---------|
| `prompt_tokens_per_second` | High (1000+) | Low (<200) = re-prefill |
| `prompt_ms` | <500ms | >2000ms = full reprocess |
| `cache_hit_rate` (logged) | 95–100% | <85% = check prefix |
| `prompt_tokens` delta | Stable (~50–200 growth) | Jump >1000 = prefix change |

## Debugging cache misses

1. **Hash the first N chars** of the system prompt across requests
2. **Compare system prompt length** — any change suggests memory/permission updates
3. **Check tool definitions** — hash the tools array
4. **Audit request timeline** — look for concurrent background requests
5. **Log provider routing** — confirm auxiliary tasks are not hitting the main endpoint
