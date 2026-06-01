# Example: Anonymized Request Timeline

This timeline shows cache behavior during a typical Hermes session
using the auxiliary routing pattern (200K context, single-slot llama-server).

## Legend

- **req**: request number
- **type**: main_chat (user message), mem_update (memory add), bg (background task)
- **messages**: total message count in the prompt
- **sys chars**: system prompt character length
- **h500**: hash of first 500 chars of system prompt
- **h8000**: hash of first 8000 chars
- **total**: total prompt character count
- **cache**: percentage of cached tokens (where available)
- **lat**: latency in seconds
- **note**: observation

## Timeline

| req | type | msg | sys chars | h500 | h2000 | h8000 | total | cache | lat | note |
|----:|------|----:|----------:|------|-------|-------|------:|------:|----:|------|
| 1 | main_chat | 115 | 28,744 | abc1 | def2 | ghi3 | 217,435 | 100% | 1.4s | warm cache |
| 2 | main_chat | 117 | 28,744 | abc1 | def2 | ghi3 | 217,563 | 100% | 1.4s | cache hit ✅ |
| 3 | main_chat | 119 | 28,744 | abc1 | def2 | ghi3 | 217,725 | 100% | 1.4s | cache hit ✅ |
| 4 | mem_update | 119 | 28,744 | abc1 | def2 | ghi3 | 218,300 | 95% | 7.3s | memory write |
| 5 | main_chat | 121 | 28,744 | **xyz9** | **uvw8** | **rst7** | 218,500 | 89% | 6.9s | partial prefill ⚠️ |
| 6 | main_chat | 123 | 28,744 | xyz9 | uvw8 | rst7 | 218,600 | 100% | 1.4s | cache recovered ✅ |
| 7 | bg(title) | 3 | 0 | — | — | — | 450 | n/a | 0.7s | auxiliary model |
| 8 | main_chat | 125 | 28,744 | xyz9 | uvw8 | rst7 | 218,750 | 100% | 1.4s | cache hit ✅ |

## Analysis

### Req 1–3: Stable turns
- Identical system prompt (`abc1/def2/ghi3`)
- 100% cache hit rate
- ~1.4s latency per turn
- **The auxiliary routing pattern is working.** Background tasks are not hitting this endpoint.

### Req 4: Memory update
- User requested saving a new fact to persistent memory
- Tool call (memory write) appended to conversation
- System prompt unchanged — cache still at 95%
- Latency slightly higher due to tool execution

### Req 5: First turn after memory update
- System prompt hashes changed (`xyz9/uvw8/rst7`) — the injected MEMORY block changed
- Cache dropped from 100% to 89%
- ~3,182 new tokens needed re-processing (partial prefill)
- **This is expected behavior.** The prefix changed, so the cache couldn't fully serve it.
- Latency: 6.9s (acceptable for a prefix change)

### Req 6: Recovery
- Second turn with the new prefix
- Cache back to 100%
- Latency back to 1.4s
- **The new prefix warmed up successfully.**

### Req 7: Background task
- Title generation triggered after the turn
- Routed to auxiliary model (not visible in this timeline — it went to a different endpoint)
- Main model slot unaffected
- **This is the key benefit of auxiliary routing.**

### Req 8: Continued stability
- Cache remains at 100%
- Latency remains at 1.4s
- No pollution from the background task

## Key takeaways

1. **Stable prefix → 100% cache hit rate.** When the system prompt doesn't change, every turn benefits from the cache.

2. **Memory updates cause ONE partial prefill, then recover.** The hash change on req 5 is expected. Req 6 immediately recovers.

3. **Auxiliary routing keeps background tasks off the main timeline.** Req 7 doesn't appear in the main endpoint's log because it went to the auxiliary provider.

4. **Without auxiliary routing**, req 7 would have hit the main endpoint, potentially evicting the slot and causing a full re-prefill on req 8.

## Generating your own timeline

Use `proxy_audit.py` (see examples/) to capture your own request timeline:

```bash
python proxy_audit.py --listen 8090 --target http://YOUR_ENDPOINT:8089/v1
```

Then analyze the log:

```bash
cat proxy_audit.jsonl | python3 -c "
import json, sys
for line in sys.stdin:
    r = json.loads(line)
    print(f'{r[\"request_id\"]:>8}  {r[\"messages_count\"]:>3}msgs  '
          f'sys={r[\"system_chars\"]:>5}ch  h500={r[\"first_500_hash\"]}  '
          f'lat={r.get(\"latency_ms\",\"?\"):>5}ms')
"
```
