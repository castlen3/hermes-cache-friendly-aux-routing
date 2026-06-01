# Troubleshooting

## Symptoms

### Frequent re-prefill on main model

Every turn feels slow. `prompt_ms` is consistently high (2000ms+). Cache hit rate logged below 80%.

**Likely causes:**
- Background tasks hitting the main endpoint
- Slot eviction (`--parallel 1` with concurrent requests)
- System prompt changing between turns (memory updates, tool changes)
- Proxy or middleware modifying requests

### Cache hit rate drops after background tasks

After `background_review` or `title_generation` completes, the next user message triggers a full prefill.

**Likely cause**: Background task used the main endpoint and evicted the KV cache slot.

### Prompt latency spikes

Randomly slow turns with no obvious pattern.

**Likely cause**: Concurrent auxiliary requests competing for the single slot, or a slow fallback chain being triggered.

### Main endpoint receives unexpected requests

You see non-conversation requests in the main endpoint's access log.

**Likely cause**: Auxiliary routing configuration is not being picked up. Check logs for "using main provider" messages.

### Background tasks hit main provider despite config

Even though `config.yaml` routes auxiliary tasks to a separate provider, logs show them still hitting the main endpoint.

**Likely cause**: Some code paths (e.g., `background_review`) may not fully respect the auxiliary config. May require a patch or provider-level routing.

## Diagnostic checks

### 1. Log actual requests

The simplest diagnostic: enable verbose logging and inspect what endpoint each request hits.

```bash
# In agent.log, look for:
grep "provider=" ~/.hermes/logs/agent.log | grep -v "main_chat"
```

### 2. Hash first 500 / 2000 / 8000 chars

Compare system prompt stability across requests:

```python
import hashlib

def hash_prefix(text, n=500):
    return hashlib.md5(text[:n].encode()).hexdigest()[:8]

# Log for each request:
# first_500_hash, first_2000_hash, first_8000_hash
```

If `first_500_hash` changes between consecutive main conversation turns (without memory changes), something is modifying the system prompt.

### 3. Compare system prompt length

```python
import json

with open("request_log.jsonl") as f:
    for line in f:
        req = json.loads(line)
        sys_msg = req["messages"][0]
        print(f"system_chars: {len(sys_msg['content'])}")
```

A stable length suggests a stable prefix. Any change indicates memory/permission/tool updates.

### 4. Compare tools hash

```python
tools_str = json.dumps(req.get("tools", []), sort_keys=True)
tools_hash = hashlib.md5(tools_str.encode()).hexdigest()[:8]
```

Changing tool definitions invalidate the cache. This is rare but worth checking.

### 5. Audit request timeline

Build a timeline of all requests to the main endpoint:

```python
# From proxy_audit.py or access log:
# request_id | timestamp | type | messages_count | total_chars | endpoint
```

Look for:
- Background requests interleaved with main conversation turns
- Concurrent requests to the same endpoint
- Requests with significantly shorter system prompts

### 6. Detect background requests

Background requests often have:
- Different or absent system prompt
- Fewer messages
- Different model name in the request body
- Specific instruction patterns ("Generate a title", "Summarize this conversation")

### 7. Check fallback target

When auxiliary tasks fail, they should fall back through the configured chain, not directly to the main endpoint.

```bash
# Look for fallback events:
grep "fallback" ~/.hermes/logs/agent.log
```

## Proxy audit setup

A lightweight Python proxy can intercept and log all requests:

```
client ──→ localhost:8090 (proxy) ──→ main endpoint (192.168.x.x:8089)
                │
                └── log: request metadata, hashes, timing
```

Key fields to log per request:

```python
{
    "request_id": "...",
    "timestamp": "...",
    "request_type": "main_chat | title_gen | web_extract | ...",
    "messages_count": 115,
    "system_chars": 28744,
    "first_500_hash": "abc12345",
    "first_2000_hash": "def67890",
    "first_8000_hash": "ghi11111",
    "tools_hash": "jkl22222",
    "total_chars": 217435,
    "endpoint": "http://192.168.x.x:8089/v1",
    "fallback": false
}
```

See `examples/proxy_audit.py` for a reference implementation.

## Quick fixes

| Symptom | Likely fix |
|---------|-----------|
| Background tasks on main endpoint | Route via `auxiliary` config |
| `background_review` not respecting config | Patch `background_review.py` to read auxiliary config |
| Slot eviction | Reduce concurrent requests; ensure `--parallel` matches concurrency |
| Memory update triggers prefill | Accept as normal; batch memory updates |
| Compression hits auxiliary model | Ensure compression is NOT routed to auxiliary |
| Fallback goes to wrong endpoint | Check `fallback_chain` ordering |
