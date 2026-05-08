# Apply Configuration Changes

Use this reference after editing `.env`, an example-local `prompts.yaml`, or an example-local `services.cloud.yaml` / `services.local.yaml`.

## Default Rule

- `.env` changes: compose re-apply.
- YAML catalog changes (`prompts.yaml`, `services.*.yaml`): compose re-apply and refresh browser. `src/` is bind-mounted, so no rebuild needed.
- `ASR_DOCKER_IMAGE`, `ASR_NIM_TAGS`, `TTS_DOCKER_IMAGE` are `.env` changes that need a compose re-apply.

## Endpoint Rules

The catalog stores Compose DNS endpoints. The backend rewrites them to `localhost` automatically when running outside Docker (`uv run`). Local entries are filtered by TCP reachability and only show in the UI when the corresponding sidecar is up.

| Compose endpoint | Host-run rewrite |
| --- | --- |
| `http://nvidia-llm:8000/v1` | `http://localhost:18000/v1` |
| `http://nvidia-llm-vllm:8000/v1` | `http://localhost:18000/v1` |
| `tts-service:50051` | `localhost:50151` |
| `asr-service:50052` | `localhost:50152` |
| `nemotron-speech:50051` | `localhost:50051` |
| `booking-server:8001` | `localhost:8001` |

Cloud catalog entries use NVCF endpoints (`grpc.nvcf.nvidia.com:443`, `https://integrate.api.nvidia.com/v1`, `wss://grpc.nvcf.nvidia.com/v1/realtime`) and are not rewritten.

## Apply Commands

`--profile` selects the example and the local sidecar set. Pick the matching profile for the example you need:

```bash
# Cloud-only (NVCF)
docker compose --profile generic up -d
docker compose --profile agentic-airline up -d

# Workstation (local NIM ASR/TTS/LLM)
docker compose --profile generic-workstation up -d
docker compose --profile agentic-airline-workstation up -d

# DGX Spark / Jetson (Generic only)
docker compose --profile generic-dgxspark up -d
docker compose --profile generic-jetson up -d

# Multi-example selector (cloud only)
docker compose --profile all-examples up -d
```

## Optional Profile Overlays

Combine with any platform profile. Re-apply must include them again to keep those services running.

### Tracing (`--profile tracing`)

Add when:
- `.env` has `ENABLE_TRACING=true`
- `OTEL_EXPORTER_OTLP_ENDPOINT` points to `phoenix:4317` or another in-repo Phoenix endpoint

### Remote WebRTC (`--profile turn`)

Add when clients connect from outside the host's network. Credentials come from `TURN_USERNAME` / `TURN_PASSWORD` in `.env` (defaults are `admin:admin`). Set `TURN_URL=turn:<host>:3478` if TURN runs on a different host. The client auto-fetches ICE config from `/api/ice-servers`.

```bash
docker compose --profile generic --profile tracing up -d
docker compose --profile generic-workstation --profile turn up -d
docker compose --profile generic-dgxspark --profile tracing --profile turn up -d
```

## Validation Checklist

- The selected `--profile` matches the example you want active.
- Multilingual prompt selection is paired with multilingual-capable ASR (`parakeet-rnnt`) and TTS (`magpie-tts`) in the active catalog.
- For S2S, the active example's `services.cloud.yaml` `s2s` block points at the desired realtime endpoint. Authentication uses `NVIDIA_API_KEY`.
- If `ENABLE_TRACING=true` with `phoenix:4317`, the `phoenix` service is started through the `tracing` profile.
- Compose-managed local entries use service DNS names, not `localhost`.
- ASR/TTS image variants keep the same endpoints (`asr-service:50052`, `tts-service:50051`).

## Verify

```bash
docker compose ps
docker compose logs --tail 200 <example-service>
```

Refresh open browser tabs after the backend is healthy. The client caches deployment metadata, built-in services, prompts, and ICE config for the page lifetime.

Verify behavior relevant to the change:
- New built-in services or prompts appear in the UI after refresh.
- Local services only appear when their containers are reachable.
- Tracing data appears in Phoenix when tracing is enabled.
