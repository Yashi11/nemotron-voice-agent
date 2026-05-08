# Configure Services

The Nemotron Voice Agent uses example-local service catalogs to manage LLM, ASR, TTS, S2S, and example-specific services (e.g. Agentic Airline `fast-llm`, `orchestrator-llm`, `booking-server`). Built-in entries come from each example's `services.cloud.yaml` (remote / NVCF) and `services.local.yaml` (Compose-managed sidecars). The active UI example determines which catalog is loaded.

## How catalog selection works

- Each example owns its catalog at `<example-package>/services.cloud.yaml` (remote / NVCF) and optional `<example-package>/services.local.yaml` (Compose-managed sidecars).
- The cloud catalog is always loaded.
- The local catalog is merged on top, but only entries whose endpoint is reachable on TCP are exposed in the UI and used by the pipeline.
- The same `--profile` works whether you run cloud-only or with local sidecars; nothing else needs to be set.

## Available services (Generic Cascaded cloud)

### LLM

| Model | Key | Description |
|-------|-----|-------------|
| [Nemotron 3 Nano 30B A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard) | `nemotron-nano` | Default. Fast, efficient reasoning model |
| [Nemotron 3 Super 120B A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard) | `nemotron-super` | Higher capability for complex tasks |

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

## Changing built-in defaults

The first entry in each catalog category is the runtime default. To change defaults, reorder entries (or add a new entry first) in the relevant `services.cloud.yaml` / `services.local.yaml` and refresh the browser. No container restart is required for catalog edits.

## On-prem catalog

`services.local.yaml` groups entries under platform sections (`workstation`, `dgxspark`, `jetson`) for documentation. The backend merges all sections automatically; reachability filtering exposes only the deployed sidecars.

| Compose endpoint | Host-run rewrite |
|---|---|
| `http://nvidia-llm:8000/v1` | `http://localhost:18000/v1` |
| `http://nvidia-llm-vllm:8000/v1` | `http://localhost:18000/v1` |
| `tts-service:50051` | `localhost:50151` |
| `asr-service:50052` | `localhost:50152` |
| `nemotron-speech:50051` | `localhost:50051` |
| `booking-server:8001` | `localhost:8001` |

## Adding built-in cloud services

Append entries to the relevant `services.cloud.yaml`. Refresh the browser to pick up the change.

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

Start the matching profile; the catalog will pick them up automatically.

```bash
docker compose --profile generic-workstation up -d
docker compose --profile generic-dgxspark up -d
docker compose --profile generic-jetson up -d
docker compose --profile agentic-airline-workstation up -d
```

`--profile generic` and `--profile agentic-airline` stay cloud-only and use only `services.cloud.yaml`.
