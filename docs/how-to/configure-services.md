# Configure Services

The Nemotron Voice Agent uses example-local service catalogs to manage LLM, ASR, TTS, and example-specific services. Built-in entries come from each example's `services.cloud.yaml` (remote / NVCF) and `services.local.yaml` (Compose-managed sidecars). The active UI example determines which catalog is loaded.

## How catalog selection works

- Each example owns its catalog at `<example-package>/services.cloud.yaml` (remote / NVCF) and optional `<example-package>/services.local.yaml` (Compose-managed sidecars).
- The cloud catalog is always loaded.
- The local catalog is merged on top, but only entries whose endpoint is reachable on TCP are exposed in the UI and used by the pipeline.
- The same `--profile` works whether you run cloud-only or with local sidecars. Nothing else needs to be set.

## Available services (Generic Cascaded cloud)

### LLM

| Model | Key | Description |
|-------|-----|-------------|
| [Nemotron 3 Nano 30B A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard) | `nemotron-nano` | Fast, efficient model (reasoning off) |
| Nemotron 3 Nano 30B A3B (Reasoning) | `nemotron-nano-reasoning` | Same model with chain-of-thought reasoning on |
| [Nemotron 3 Super 120B A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard) | `nemotron-super` | Higher capability for complex tasks (reasoning off) |
| Nemotron 3 Super 120B A12B (Reasoning) | `nemotron-super-reasoning` | Same model with chain-of-thought reasoning on |

> The active default per slot is set in `examples_registry.yaml` (`defaults`), not by this table. See [Changing built-in defaults](#changing-built-in-defaults).

### ASR

| Model | Key | Description |
|-------|-----|-------------|
| [Nemotron ASR Streaming](https://build.nvidia.com/nvidia/nemotron-asr-streaming/modelcard) | `nemotron-asr-streaming-english` | Default. Low-latency English ASR |
| [Parakeet CTC 1.1B](https://build.nvidia.com/nvidia/parakeet-ctc-1_1b-asr/modelcard) | `parakeet-ctc` | English ASR |
| [Parakeet 1.1B RNNT Multilingual](https://build.nvidia.com/nvidia/parakeet-1_1b-rnnt-multilingual-asr/modelcard) | `parakeet-rnnt` | Multilingual ASR |

### TTS

| Model | Key | Description |
|-------|-----|-------------|
| [Magpie TTS Multilingual](https://build.nvidia.com/nvidia/magpie-tts-multilingual/modelcard) | `magpie-tts` | Default. Multilingual text-to-speech |

## Switching services in the UI

The Services tab lists all services exposed by the active catalog (cloud and reachable local entries). Click an entry to make it the active selection for that category. Selections persist in browser localStorage. Custom services added through the UI also live in localStorage.

## LLM reasoning (thinking) on/off

Nemotron LLMs support a chain-of-thought "thinking" mode. It is controlled per
catalog entry through `extra_params`, which is forwarded to the model as
`extra_body`:

```yaml
llm:
  # Reasoning OFF — lowest latency (recommended default for spoken pipelines)
  nemotron-nano:
    model_id: "nvidia/nemotron-3-nano-30b-a3b"
    extra_params: '{"extra_body":{"chat_template_kwargs":{"enable_thinking":false}}}'

  # Reasoning ON — better on complex tasks, higher time-to-first-response
  nemotron-nano-reasoning:
    model_id: "nvidia/nemotron-3-nano-30b-a3b"
    extra_params: '{"extra_body":{"chat_template_kwargs":{"enable_thinking":true}}}'
```

- Reasoning OFF: `chat_template_kwargs.enable_thinking: false`. Reasoning ON: `enable_thinking: true`.
- The `*-reasoning` variants work on **cloud and on-prem**. Cloud has the parsers enabled server-side; self-hosted (NIM or raw vLLM) needs `--reasoning-parser nemotron_v3` so reasoning is separated and TTS speaks only `content`. Local `*-reasoning` entries ship for **workstation** and **dgxspark** in `services.local.yaml`. See [Troubleshooting](#troubleshooting-tool-calling--reasoning) if local tools return HTTP 400 or reasoning leaks.
- Select a variant from the Services tab, or set it as the default in `examples_registry.yaml`.

## Changing built-in defaults

Each example declares its default service per slot via `defaults` in `examples_registry.yaml`. The pipeline resolves that default at startup, and the UI uses it as the initial selection. Edit `defaults` (and optionally reorder entries in the `services.cloud.yaml` / `services.local.yaml` for visual ordering in the UI) to change defaults. Host-run development reads these files directly. The Docker images mount `./src` and `./examples_registry.yaml` read-only so changes are picked up after `docker compose restart <service>`.

When the same default key exists in both `services.cloud.yaml` and `services.local.yaml`, the resolver prefers the **self-hosted** variant so that deploying local NIM sidecars automatically promotes them to the active default — no UI click needed. If the self-hosted endpoint is unreachable at session-start time, the runtime falls back to the cloud variant.

> **On-prem note:** self-hosted promotion only applies when the `defaults` key also exists in `services.local.yaml`. A default whose key exists **only** in `services.cloud.yaml` resolves to the cloud model even on an on-prem recipe — point `defaults` at a local key or pick the model from the Services tab.

## On-prem catalog

`services.local.yaml` groups entries under platform sections (`workstation`, `dgxspark`, `jetson`) for documentation. The backend merges all sections automatically. Reachability filtering exposes only the deployed sidecars.

| Compose endpoint | Host-run rewrite |
|---|---|
| `http://nvidia-llm:8000/v1` | `http://localhost:18000/v1` |
| `http://nvidia-llm-vllm:8000/v1` | `http://localhost:18000/v1` |
| `http://nvidia-llm-vllm-omni:8002/v1` | `http://localhost:8002/v1` |
| `tts-service:50051` | `localhost:50151` |
| `nemotron-asr-streaming-english:50052` | `localhost:50152` |
| `nemotron-asr-streaming-multilingual:50052` | `localhost:50152` |
| `parakeet-ctc-asr:50052` | `localhost:50152` |
| `parakeet-rnnt-asr:50052` | `localhost:50152` |
| `nemotron-speech:50051` | `localhost:50051` |

## Adding built-in cloud services

Append entries to the relevant `services.cloud.yaml`. Refresh the browser for host-run development, or rebuild/redeploy Docker to package the change into the image.

```yaml
llm:
  my-custom-llm:
    name: "My Custom LLM"
    model_id: "org/model-name"
    base_url: "https://integrate.api.nvidia.com/v1"
    system_prompt: ""
    extra_params: ""
```

```yaml
asr:
  my-custom-asr:
    name: "My Custom ASR"
    server: "grpc.nvcf.nvidia.com:443"
    model: "my-asr-model"
    function_id: ""
```

```yaml
tts:
  my-custom-tts:
    name: "My Custom TTS"
    server: "grpc.nvcf.nvidia.com:443"
    voice_id: "Magpie-Multilingual.EN-US.Aria"
    function_id: ""
```

## Local NIM services

Pick the recipe profile that matches the example and hardware target. The catalog picks up the matching sidecars automatically once they are reachable.

```bash
docker compose --profile generic-assistant/workstation up -d
docker compose --profile generic-assistant/dgx-spark up -d
docker compose --profile generic-assistant/jetson-thor up -d
docker compose --profile multilingual-assistant/workstation up -d
docker compose --profile multilingual-assistant/dgx-spark up -d
docker compose --profile omni-assistant/workstation up -d
docker compose --profile omni-assistant/dgx-spark up -d
docker compose --profile omni-assistant-subagents/workstation up -d
docker compose --profile omni-assistant-subagents/dgx-spark up -d
docker compose --profile thinker-talker/workstation up -d
```

Running a cloud-only profile (e.g. `--profile generic-assistant`) stays cloud-only and uses just `services.cloud.yaml`.

## Troubleshooting: tool calling & reasoning

Self-hosted Nemotron-3 only — cloud (NVCF) has the parsers enabled server-side. The repo's `docker/docker-compose.nemotron3-*.yaml` already set these.

- **`HTTP 400: "auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser`** -> the 2.x builds don't auto-enable the parsers. Pass them on the LLM service — NIM: `NIM_PASSTHROUGH_ARGS=--enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser nemotron_v3`; raw vLLM (DGX-Spark/Jetson): the same flags on `vllm serve`.
- **Reasoning is spoken by TTS / `<think>` leaks into the answer** -> the reasoning parser isn't set; add `--reasoning-parser nemotron_v3` (separates reasoning from `content` and keeps reasoning-OFF working).
- **Raw vLLM: `nemotron_v3` not found, or Super won't load (`MIXED_PRECISION`)** -> the image's vLLM is too old. Use NGC `nvcr.io/nvidia/vllm:26.05.post1-py3` (vLLM ≥ 0.20 ships both); `nvcr.io/nvidia/vllm:25.12.post1-py3` (0.12.0) lacks them — upgrade or mount a plugin via `--reasoning-parser-plugin`.
