# Configure Services

The Nemotron Voice Agent uses example-local service catalogs to manage LLM, ASR, TTS, S2S, and example-specific services. Built-in entries come from each example's `services.cloud.yaml` (remote / NVCF) and `services.local.yaml` (Compose-managed sidecars). The active UI example determines which catalog is loaded.

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
| Nemotron Speech Streaming En 0.6B | `nemotron-speech` | Default. Low-latency English ASR |
| [Parakeet CTC 1.1B](https://build.nvidia.com/nvidia/parakeet-ctc-1_1b-asr/modelcard) | `parakeet-ctc` | English ASR |
| [Parakeet 1.1B RNNT Multilingual](https://build.nvidia.com/nvidia/parakeet-1_1b-rnnt-multilingual-asr/modelcard) | `parakeet-rnnt` | Multilingual ASR |

### TTS

| Model | Key | Description |
|-------|-----|-------------|
| [Magpie TTS Multilingual](https://build.nvidia.com/nvidia/magpie-tts-multilingual/modelcard) | `magpie-tts` | Default. Multilingual text-to-speech |

### S2S (Speech-to-Speech)

| Model | Key | Description |
|-------|-----|-------------|
| [Nemotron Voice Chat](https://build.nvidia.com/nvidia/nemotron-voicechat) | `nemotron-voice-chat` | Direct voice-to-voice pipeline |

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
- The `*-reasoning` variants are **cloud (NVCF) only**. On NVCF the thinking comes back in a separate `reasoning_content` field, so TTS speaks only the final answer (`content`); the local Nano NIM emits it inline in `content`, so reasoning isn't offered on-prem.
- Select a variant from the Services tab, or set it as the default in `examples_registry.yaml`.

## Changing built-in defaults

Each example declares its default service per slot via `defaults` in `examples_registry.yaml`. The pipeline resolves that default at startup, and the UI uses it as the initial selection. Edit `defaults` (and optionally reorder entries in the `services.cloud.yaml` / `services.local.yaml` for visual ordering in the UI) to change defaults. Host-run development reads these files directly. The Docker images mount `./src` and `./examples_registry.yaml` read-only so changes are picked up after `docker compose restart <service>`.

When the same default key exists in both `services.cloud.yaml` and `services.local.yaml`, the resolver prefers the **self-hosted** variant so that deploying local NIM sidecars automatically promotes them to the active default — no UI click needed. If the self-hosted endpoint is unreachable at session-start time, the runtime falls back to the cloud variant.

> **On-prem note:** self-hosted promotion only applies when the `defaults` key also exists in `services.local.yaml`. A default with no on-prem entry (e.g. a cloud-only `nemotron-super`) resolves to the cloud model even on an on-prem recipe — point `defaults` at a local key or pick the model from the Services tab.

## On-prem catalog

`services.local.yaml` groups entries under platform sections (`workstation`, `dgxspark`, `jetson`) for documentation. The backend merges all sections automatically. Reachability filtering exposes only the deployed sidecars.

| Compose endpoint | Host-run rewrite |
|---|---|
| `http://nvidia-llm:8000/v1` | `http://localhost:18000/v1` |
| `http://nvidia-llm-vllm:8000/v1` | `http://localhost:18000/v1` |
| `http://nvidia-llm-vllm-omni:8002/v1` | `http://localhost:8002/v1` |
| `tts-service:50051` | `localhost:50151` |
| `asr-service:50052` | `localhost:50152` |
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
docker compose --profile cascaded-generic/workstation up -d
docker compose --profile cascaded-generic/dgx-spark up -d
docker compose --profile cascaded-generic/jetson-thor up -d
docker compose --profile cascaded-omni/workstation up -d
docker compose --profile cascaded-omni/dgx-spark up -d
docker compose --profile cascaded-thinker-talker/workstation up -d
```

Running a cloud-only profile (e.g. `--profile cascaded-generic`) stays cloud-only and uses just `services.cloud.yaml`.
