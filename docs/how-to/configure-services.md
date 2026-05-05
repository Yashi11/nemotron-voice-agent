# Configure Services

The Nemotron Voice Agent uses a service catalog to manage LLM, ASR, TTS, and S2S endpoints. Built-in entries come from [`services.cloud.yaml`](../../services.cloud.yaml) (remote / NVCF) or [`services.local.yaml`](../../services.local.yaml) (on-prem). Set `DEPLOYMENT_PLATFORM` in `.env` to `workstation`, `dgxspark`, or `jetson` when you want the local catalog; leave it unset for remote/NVCF mode. You can also add services at runtime from the UI or switch them from the UI dropdowns.

## Which catalog is active

The `--profile` flag selects both the example (Generic vs. Agentic Airline) and the platform. The Generic example is shown below; substitute `agentic-airline` / `agentic-airline-workstation` for the Agentic Airline example.

| `.env` setting | Launch command | Catalog file |
|----------------|----------------|--------------|
| `DEPLOYMENT_PLATFORM` unset | `docker compose --profile generic up -d` | [`services.cloud.yaml`](../../services.cloud.yaml) |
| `DEPLOYMENT_PLATFORM=workstation` | `docker compose --profile generic-workstation up -d` | [`services.local.yaml`](../../services.local.yaml) (`workstation:` section) |
| `DEPLOYMENT_PLATFORM=dgxspark` | `docker compose --profile generic-dgxspark up -d` | [`services.local.yaml`](../../services.local.yaml) (`dgxspark:` section) |
| `DEPLOYMENT_PLATFORM=jetson` | `docker compose --profile generic-jetson up -d` | [`services.local.yaml`](../../services.local.yaml) (`jetson:` section) |

Always keep `DEPLOYMENT_PLATFORM` in `.env` aligned with the `--profile` you launch. The same `.env` setting is honored for non-Docker (`uv run`) workflows.

## Available Services (cloud catalog)

The default [`services.cloud.yaml`](../../services.cloud.yaml) includes:

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

On-prem defaults live in [`services.local.yaml`](../../services.local.yaml); edit hostnames and keys to match your stack.

## Switching Services via the UI

The client UI includes dropdowns for LLM, ASR, and TTS services. Select any service from the dropdown to switch during a session. The change takes effect on the next conversation turn.

## Adding Custom Services via the UI

You can add custom services directly from the UI's **Services** tab without editing any files or restarting the server. Custom services added in the UI are stored in the browser's localStorage and persist across sessions.

## Changing Default Services

Edit the `.env` file only when you want to override the deployment defaults. If a configured key is missing from the active catalog, the backend falls back to the first built-in entry in that category:

```bash
DEFAULT_LLM=nemotron-nano
DEFAULT_TTS=magpie-tts
DEFAULT_ASR=nemotron-speech
```

## On-prem catalog (`services.local.yaml`)

Edit [`services.local.yaml`](../../services.local.yaml) for Jetson, DGX Spark, or workstation deployments. The shipped file groups entries under `workstation:`, `dgxspark:`, and `jetson:` and keeps only the available built-ins for each deployment:

- `workstation`: `http://nvidia-llm:8000/v1`, `asr-service:50052`, `tts-service:50051`
- `dgxspark`: `http://nvidia-llm-vllm:8000/v1`, `asr-service:50052`, `tts-service:50051`
- `jetson`: `http://nvidia-llm-vllm:8000/v1`, `nemotron-speech:50051` (compose-managed Riva serves ASR and TTS on the same port)

Edit [`services.local.yaml`](../../services.local.yaml) directly for your deployment.

## Adding built-in services (cloud)

To add NVCF-oriented built-in options for cloud deployments, edit [`services.cloud.yaml`](../../services.cloud.yaml). Changes are picked up without rebuilding the image when the file is bind-mounted; refresh the browser if the UI caches the catalog.

### LLM Example

```yaml
llm:
  my-custom-llm:
    name: "My Custom LLM"
    model_id: "org/model-name"
    base_url: "https://integrate.api.nvidia.com/v1"
    system_prompt: ""
    extra_params: ""
```

### ASR Example

```yaml
asr:
  my-custom-asr:
    name: "My Custom ASR"
    server: "grpc.nvcf.nvidia.com:443"
    model: "my-asr-model"
    function_id: ""
```

### TTS Example

```yaml
tts:
  my-custom-tts:
    name: "My Custom TTS"
    server: "grpc.nvcf.nvidia.com:443"
    voice_id: "Magpie-Multilingual.EN-US.Aria"
    function_id: ""
```

## Using Local NIM Services

When deploying with Docker Compose profiles, ASR, TTS, and LLM services run on your hardware. Set `DEPLOYMENT_PLATFORM` in `.env` so the backend loads the matching section from [`services.local.yaml`](../../services.local.yaml), then start the matching profile:

```bash
# .env
DEPLOYMENT_PLATFORM=workstation   # or dgxspark / jetson
```

```bash
docker compose --profile generic-workstation up -d
docker compose --profile generic-dgxspark up -d
docker compose --profile generic-jetson up -d

# Agentic Airline example (workstation)
docker compose --profile agentic-airline-workstation up -d
```

Running `docker compose --profile generic up -d` (or `docker compose --profile agentic-airline up -d`) with `DEPLOYMENT_PLATFORM` unset stays cloud-only and loads [`services.cloud.yaml`](../../services.cloud.yaml).
