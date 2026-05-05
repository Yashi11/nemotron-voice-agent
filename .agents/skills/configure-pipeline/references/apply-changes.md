# Apply Configuration Changes

Use this reference after editing `.env`, `services.cloud.yaml`, `services.local.yaml`, or `prompt.yaml`.

## Default Rule

Configuration changes use compose re-apply without rebuilding images. Reserve `--build` for source code or `Dockerfile` changes.

- `.env` changes require a compose re-apply because environment variables and startup defaults are read at container start.
- `services.cloud.yaml`, `services.local.yaml`, and `prompt.yaml` catalog changes are read by the backend without a container restart, but open browser tabs cache built-in services and prompts aggressively. Begin with a browser refresh.
- Re-apply the deployment after YAML-only changes only when containers are stopped, startup defaults must be reloaded, or the deployment state must be re-applied explicitly.
- Local image overrides such as `ASR_DOCKER_IMAGE`, `ASR_NIM_TAGS`, and `TTS_DOCKER_IMAGE` are `.env` changes. Re-apply Compose. Rebuild the application image (`nemotron-voice-agent:latest`, shared by every example service) only when source files or the `Dockerfile` changed.

## Endpoint Rules by Deployment Style

- Cloud services: keep the built-in cloud endpoints unless a different remote service is requested explicitly.
- Compose-managed `workstation`: LLM `http://nvidia-llm:8000/v1`, ASR `asr-service:50052`, TTS `tts-service:50051`
- Compose-managed `dgxspark`: LLM `http://nvidia-llm-vllm:8000/v1`, ASR `asr-service:50052`, TTS `tts-service:50051`
- Host-run backend outside Docker: `localhost:18000/v1`, `localhost:50152`, and `localhost:50151` are valid local endpoints.
- Compose-managed `jetson`: LLM `http://nvidia-llm-vllm:8000/v1`, ASR/TTS `nemotron-speech:50051` (Riva serves both on the same port)

## Apply Commands by Mode

When a compose re-apply is required, use the current deployment mode rather than the target hardware in general. Local profiles expect `DEPLOYMENT_PLATFORM` to be set in `.env` to the matching value. Cloud-only requires it to be unset.

The `--profile` flag combines the example name (`generic` or `agentic-airline`) with the platform suffix. Substitute `agentic-airline*` when running the Agentic Airline example; the Generic example is shown below.

### Cloud-Only

```bash
# DEPLOYMENT_PLATFORM unset in .env
docker compose --profile generic up -d
# or: docker compose --profile agentic-airline up -d
```

### Workstation

```bash
# DEPLOYMENT_PLATFORM=workstation in .env
docker compose --profile generic-workstation up -d
# or: docker compose --profile agentic-airline-workstation up -d
```

### DGX Spark

```bash
# DEPLOYMENT_PLATFORM=dgxspark in .env
docker compose --profile generic-dgxspark up -d
```

### Jetson

```bash
# DEPLOYMENT_PLATFORM=jetson in .env
docker compose --profile generic-jetson up -d
```

## Optional Profile Overlays

Combine with any platform profile. Preserve whichever overlays were active at last deploy. Re-apply must include them again to keep those services running.

### Tracing (`--profile tracing`)

Add when both:

- `.env` has `ENABLE_TRACING=true`
- `OTEL_EXPORTER_OTLP_ENDPOINT` points to `phoenix:4317` or another in-repo Phoenix endpoint

Skip it if tracing is disabled or the collector is external.

### Remote WebRTC (`--profile turn`)

Add when clients connect from outside the host's network (NAT / firewall). LAN-only deployments work without it. Credentials come from `TURN_USERNAME` / `TURN_PASSWORD` in `.env`. Defaults are `admin:admin`. Override them for production. If TURN is deployed on a different host than the voice agent, set `TURN_URL=turn:<turn-host-or-ip>:3478`. The client auto-fetches ICE config from `/api/ice-servers`.

### Examples

```bash
docker compose --profile generic --profile tracing up -d
docker compose --profile generic-workstation --profile tracing up -d
docker compose --profile generic-workstation --profile turn up -d
docker compose --profile generic-dgxspark --profile tracing --profile turn up -d
```

## When Re-Apply Is Needed

- `.env` changes: always re-apply. Environment variables are read at container start.
- ASR/TTS image overrides: re-apply the same active profile after `docker login` if the override image requires registry access.
- Service catalog YAML changes: refresh the browser first. Re-apply only if containers are stopped or startup defaults must be reloaded.
- `prompt.yaml` changes: refresh the browser first. Re-apply only if containers are stopped or startup defaults must be reloaded.

## Validation Checklist

- `DEPLOYMENT_PLATFORM` in `.env` matches the launched `--profile` (both `workstation`, both `dgxspark`, both `jetson`, or both absent for cloud-only)
- If `DEFAULT_LLM`, `DEFAULT_ASR`, or `DEFAULT_TTS` are set, they should point to keys that exist in the active catalog. Otherwise, the first built-in entry in that category is used.
- `PROMPT_SELECTOR` points to a key that exists in `prompt.yaml`
- Multilingual prompt selection is paired with multilingual-capable ASR and TTS from the active catalog. Use `magpie-tts` for TTS and `parakeet-rnnt` for ASR; verify the key exists before setting it.
- The S2S pipeline uses `NVIDIA_API_KEY` for authentication. Edit the `s2s` block in `services.cloud.yaml` (or pick a different entry from the UI) when targeting a non-default realtime endpoint.
- If `ENABLE_TRACING=true` with `phoenix:4317`, the `phoenix` service is started through the `tracing` profile
- Compose-managed local entries use service DNS names, not `localhost`
- Compose-managed ASR/TTS image variants keep the same endpoints: `asr-service:50052` and `tts-service:50051`.
- Compose-managed `workstation` uses 2 GPUs: ASR/TTS on GPU `0`, and the NIM LLM on GPU `1`.

## Local Endpoint Notes

- `localhost` points back to the example container (whichever variant is running) when the backend runs under Docker Compose.
- For Compose-managed `workstation`, use `http://nvidia-llm:8000/v1`, `asr-service:50052`, and `tts-service:50051`.
- For Compose-managed `dgxspark`, use `http://nvidia-llm-vllm:8000/v1`, `asr-service:50052`, and `tts-service:50051`.
- For DGX Spark TTS image overrides, keep `tts-service:50051` and set `TTS_DOCKER_IMAGE` in `.env`.
- Use `localhost` local endpoints only for host-run backend workflows outside Docker.
- For Compose-managed `jetson`, use `http://nvidia-llm-vllm:8000/v1` and `nemotron-speech:50051` (Riva serves ASR and TTS on the same port).

## Mode Detection Hints

If the current deployment mode is not already known, inspect running services:

```bash
docker compose ps --services --status running
```

Interpret the result with these heuristics:

- `nvidia-llm` running -> `workstation`
- `nvidia-llm-vllm`, `asr-service`, and `tts-service` running -> `dgxspark`
- `nvidia-llm-vllm` and `nemotron-speech` running -> `jetson`
- only an example service running with no NIM sidecars (one of `all-examples`, `generic-example`, or `agentic-airline-example`) -> likely `cloud-only`
- `phoenix` can appear alongside any mode

If the output is ambiguous, confirm the deployment mode instead of guessing.

## Verify

After applying config changes:

```bash
docker compose ps
# Service name varies by profile: `all-examples`, `generic-example[-suffix]`,
# or `agentic-airline-example[-suffix]`. Read it from `ps` output.
docker compose logs --tail 200 <example-service>
```

Refresh any open browser tabs after the backend is healthy. The client caches deployment metadata, built-in services, prompts, and ICE server config for the lifetime of the page.

Also verify the behavior relevant to the change:

- built-in services or prompts added through YAML appear in the UI after refresh
- validate `.env` defaults against the active catalog or API response. Browser localStorage may preserve earlier UI selections
- tracing data appears in Phoenix when tracing was enabled
- multilingual prompt changes produce the expected structured output
- local endpoints respond as expected in the selected deployment mode
