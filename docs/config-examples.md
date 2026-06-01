# Configuration Examples

This document provides concrete configuration examples for routing auxiliary tasks to various provider types.

All examples assume Hermes-style `config.yaml` with an `auxiliary` section.

## Generic template

```yaml
auxiliary:
  title_generation:
    provider: aux-model
    model: your-aux-model-id
    fallback_chain:
      - provider: default-cloud-provider
        model: cheap-model

  web_extract:
    provider: aux-model
    model: your-aux-model-id
    fallback_chain:
      - provider: default-cloud-provider
        model: cheap-model

  session_search:
    provider: aux-model
    model: your-aux-model-id
    fallback_chain:
      - provider: default-cloud-provider
        model: cheap-model

  background_review:
    provider: aux-model
    model: your-aux-model-id
    fallback_chain:
      - provider: default-cloud-provider
        model: cheap-model

  compression:
    provider: auto
    # compression stays on default routing — do NOT route to auxiliary
```

## Example 1: Local LM Studio

A Mac or PC running LM Studio on the local network.

```yaml
providers:
  mac-local:
    base_url: http://localhost:1234/v1
    default_model: qwen/qwen3.5-35b-a3b
    model: qwen/qwen3.5-35b-a3b
    api_key: lm-studio
    discover_models: false

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

## Example 2: Remote LAN endpoint

A secondary machine on the same network running llama-server or Ollama.

```yaml
providers:
  aux-lan:
    base_url: http://192.168.1.100:1234/v1
    default_model: qwen3.5-14b
    model: qwen3.5-14b
    api_key: not-needed
    discover_models: false

auxiliary:
  title_generation:
    provider: aux-lan
    model: qwen3.5-14b
  web_extract:
    provider: aux-lan
    model: qwen3.5-14b
  session_search:
    provider: aux-lan
    model: qwen3.5-14b
  background_review:
    provider: aux-lan
    model: qwen3.5-14b
  compression:
    provider: auto
```

Replace IP and model with your own endpoint.

## Example 3: Cloud cheap model (OpenRouter)

Using a cheap cloud model for auxiliary tasks — good when you don't have local hardware.

```yaml
providers:
  cheap-cloud:
    provider: openrouter
    model: deepseek/deepseek-chat
    # or: google/gemini-2.5-flash-lite, meta-llama/llama-4-scout

auxiliary:
  title_generation:
    provider: cheap-cloud
    model: deepseek/deepseek-chat
  web_extract:
    provider: cheap-cloud
    model: deepseek/deepseek-chat
  session_search:
    provider: cheap-cloud
    model: deepseek/deepseek-chat
  background_review:
    provider: cheap-cloud
    model: deepseek/deepseek-chat
  compression:
    provider: auto
```

## Example 4: Hybrid routing

Different tasks have different quality requirements.

```yaml
auxiliary:
  title_generation:
    provider: cheap-cloud
    model: deepseek/deepseek-chat

  web_extract:
    provider: cheap-cloud
    model: deepseek/deepseek-chat

  session_search:
    provider: aux-lan
    model: qwen3.5-14b
    # session search benefits from local speed

  background_review:
    provider: aux-lan
    model: qwen3.5-35b-a3b
    # review quality matters more than title generation

  compression:
    provider: auto
    # always use best available for compression
```

## Example 5: Provider block (inline definition)

For aux providers that don't need a full provider block:

```yaml
auxiliary:
  title_generation:
    provider: inline
    base_url: http://localhost:8080/v1
    model: small-model
    api_key: local-key
```

## Case study: 200K context llama-server with local auxiliary Mac

Real-world configuration from a production Hermes setup:

- **Main model**: Qwen3.6 27B GGUF via llama-server (port 8089)
  - Context: 200,000 tokens
  - Cache: `--cache-prompt --cache-reuse 256`
  - Draft: MTP spec draft
  - GPU: NVIDIA RTX 3090 24GB VRAM
- **Auxiliary model**: Qwen3.5 35B A3B via LM Studio (separate Mac, port 1234)
  - MoE architecture, fast inference
  - 16GB unified memory

```yaml
auxiliary:
  title_generation:
    provider: mac-local
    model: qwen/qwen3.5-35b-a3b
    fallback_chain:
      - provider: opencode-go
        model: deepseek-chat
  web_extract:
    provider: mac-local
    model: qwen/qwen3.5-35b-a3b
    fallback_chain:
      - provider: opencode-go
        model: deepseek-chat
  session_search:
    provider: mac-local
    model: qwen/qwen3.5-35b-a3b
    fallback_chain:
      - provider: opencode-go
        model: deepseek-chat
  background_review:
    provider: mac-local
    model: qwen/qwen3.5-35b-a3b
  compression:
    provider: auto
```

**Results**: Main conversation cache hit rate stabilized at ~100% on consecutive turns. Memory updates still cause one-time partial prefill (expected — the system prompt prefix changes), but cache recovers on the next turn.

> **Note**: Replace IP addresses and model IDs with your own endpoints. The pattern works with any OpenAI-compatible API.
