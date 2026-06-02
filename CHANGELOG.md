# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Two new cascaded examples — `cascaded/omni-assistant` (Nemotron 3 Nano Omni as a single multimodal ASR + LLM service with Magpie TTS) and `cascaded/omni-assistant-subagents` (the same Omni service split across four cooperating Pipecat Subagents with live webcam vision and uploaded-media analysis)
- `NvidiaOmniMultimodalService` — an upstream-compatible Pipecat `LLMService` for Nemotron Omni, with the application-policy extension hooks `_on_turn_result`, `_structured_response_control_fields`, `_should_emit_streamed_structured_response`
- Generic `capabilities` field per example in `examples_registry.yaml` (`attachments`, `webcam`). The UI gates the attachment-upload control and the webcam panel on these capabilities so no example-specific code lives in the client
- New session-scoped HTTP endpoints `POST /api/sessions/{session_id}/attachments`, `POST /api/sessions/{session_id}/webcam/frames`, `GET /api/webcam-config` (capability-driven, not example-named)
- Generic client-visible `metric-group` server-message protocol for the Metrics panel. Any pipeline can publish grouped per-turn metrics
- Recipe-style compose profiles (`<family>/<example>` for cloud-only and `<family>/<example>/<hardware>` for on-prem). Every profile is a complete, self-contained deployment stack — no orthogonal hardware profile to combine, no silent mis-pairing
- `pipecat-ai-subagents>=0.6.0` declared in `pyproject.toml` (consumed by `cascaded/omni-assistant-subagents`)
- `examples_registry.yaml` becomes the single source of truth for which examples and transports the UI exposes (`selection`, `transports` fields) and per-example slot defaults (`defaults`). `EXAMPLE_SELECTION` / `TRANSPORT_SELECTION` env vars provide runtime overrides without surfacing in `.env.example`
- Compose recipes are named after the registry key for cloud-only deployments and append hardware for on-prem deployments (for example, `cascaded/generic/dgxspark`). Observability profiles (`tracing`, `turn`) remain optional overlays.
- `nemotron-speech` compose service promotes Riva (ASR + TTS) to a first-class Jetson service so the full stack lifecycles via `docker compose --profile cascaded/generic/jetson up -d`. Replaces the prior host-side `riva_start.sh` flow
- CUDA MPS SM-split and disjoint CPU pinning for Thor's shared GPU and LPDDR5X bus: `VLLM_MPS_THREAD_PCT` / `RIVA_MPS_THREAD_PCT` and `VLLM_CPUSET` / `RIVA_CPUSET` / `PIPECAT_CPUSET`. `scripts/start-mps.sh` and `scripts/stop-mps.sh` manage the daemon
- Grouped service UI (Self-hosted / NVIDIA Cloud / Custom) in the LLM/ASR/TTS selectors, driven by namespaced service IDs returned by `/api/services`
- `APP_RUNTIME=container` marker set by `docker-compose.yml`. When absent the backend rewrites Compose-reachable endpoints in `services.local.yaml` to `localhost` so host-native runs (`uv run`) work without editing the catalog
- TCP reachability filter on `/api/services`: only deployed local services appear in the UI. Cloud entries always show
- Pre-commit hook config (`uv run ruff check`, `uv run ruff format`, `npm run lint`)
- Speech-to-Speech now has its own example-local catalog under `src/speech_to_speech/generic/`

### Changed

- Single root `docker-compose.yml` now hosts one `x-app` template plus per-example service variants (`cascaded-generic`, `cascaded-omni-assistant`, `cascaded-omni-assistant-subagents`, `speech-to-speech-generic`)
- Compose profile model switched from two orthogonal axes (`<example>` × `<hardware>`) to single recipe profiles (`<family>/<example>/<hardware>`). Each recipe is a complete deployment stack, so wrong-combo deployments become impossible to type. Replaces the previous `--profile <example> --profile <hardware>` style and the short-lived `dgxspark-omni` / `jetson-omni` hardware-suffix profiles
- Pipelines default slot values come from `examples_registry.yaml` `defaults` rather than YAML insertion order, so YAML reformats do not silently change behavior
- Registry-default service resolution now prefers the `self-hosted` variant over `cloud-nim` when both define the same key, matching `/api/services` precedence so local NIM sidecars become the active default as soon as they're deployed
- Jetson ASR/TTS endpoint moves from `host.docker.internal:50051` to the `nemotron-speech:50051` compose service. Host-run Pipecat rewrites it to `localhost:50051` automatically
- Service catalogs are example-local: each example owns `services.cloud.yaml` and `services.local.yaml`. The local catalog is merged on top of the cloud catalog when its endpoints are reachable. Selection no longer relies on a `DEPLOYMENT_PLATFORM` flag
- S2S pipeline now authenticates with `NVIDIA_API_KEY` only. The former `S2S_API_KEY` env fallback (with OpenAI compatibility) has been removed

### Removed

- Example/pipeline-shaping CLI flags from `src/server.py`: `--example`, `--bot`, `--all-examples`, `--pipeline`, `--transport`. Their behavior moves to `examples_registry.yaml` (`selection`, `transports`, `defaults`) plus optional env overrides. CLI args now cover only infrastructure concerns (`--host`, `--port`, `--prompt-file`, `--tls-cert`/`--tls-key`, `--workers`, `-v`)
- `DEFAULT_PIPELINE_MODE` environment variable (superseded by `EXAMPLE_SELECTION`)
- Per-example compose files for `cascaded/generic` (no example-specific sidecars to ship). Generic example now uses only the root compose template
- `--profile all-examples`, `--profile generic[-*]`, and standalone hardware profiles such as `workstation`, `dgxspark`, and `jetson` (replaced by self-contained recipe profiles)
- `LLM_INTERLEAVING` env flag and `NvidiaInterleavedLLMService`: MPS + CPU pinning replace the need for strict sentence-bounded interleaving
- `S2S_API_KEY` environment variable
- `DEPLOYMENT_PLATFORM`, `DEFAULT_LLM`, `DEFAULT_ASR`, `DEFAULT_TTS`, `BOOKING_API_URL`, `FAST_LLM_*`, and `ORCHESTRATOR_LLM_*` env vars. Configuration now lives entirely in the example service catalogs
- Root-level `services.cloud.yaml` / `services.local.yaml` (replaced by example-local catalogs)

## [2.0.0] - 2026-03-25

Major architecture upgrade: new Pipecat-based pipeline with speech-to-speech support, unified React client, and flexible deployment profiles.

### Added

- **Speech-to-speech pipeline mode** using Nemotron Voice Chat for direct voice-to-voice conversations
- **Cascaded pipeline mode** with separate ASR → LLM → TTS services, selectable from the UI
- Unified React/Vite client (`client/`) replacing the previous `frontend/` WebRTC and WebSocket UIs
- `services.yaml` service catalog for configuring LLM, ASR, TTS, and S2S endpoints
- Example-local `prompts.yaml` catalogs for persona/system prompt presets selectable from the UI
- Docker Compose profiles for flexible deployment:
  - `workstation`: local ASR + TTS + LLM sidecars
  - `dgxspark`: 1 GPU — ASR + TTS NIMs + vLLM LLM on GPU 0
  - `jetson`: 1 GPU — host-side ASR + TTS + vLLM LLM on GPU 0 (later replaced by the compose-managed `nemotron-speech` Riva service)
- Additional LLM option: Nemotron 3 Super 120B A12B
- Additional ASR option: Nemotron Speech Streaming En 0.6B
- Local development support via `uv` without Docker
- HTTPS by default on the server endpoint

### Changed

- Upgraded Pipecat from 0.0.98 to 0.0.107
- Removed `nvidia-pipecat` Git submodule dependency (Pipecat services used directly)
- Replaced separate `docker-compose.yml` and `docker-compose.jetson.yml` with a single `docker-compose.yml` using profiles
- Moved environment config from `config/env.example` to `.env.example` at repo root
- Server entry point changed from `src/pipeline.py` / `src/pipeline_websocket.py` to `src/server.py`
- Default deployment mode is now cloud-only (no local GPUs required)

### Removed

- `nvidia-pipecat` Git submodule
- `frontend/` directory (replaced by `client/`)
- `config/` directory (replaced by root-level `.env.example` and example-local YAML catalogs)
- Separate Jetson Docker Compose file

## [1.0.0] - 2025-03-03

Initial release of Nemotron Voice Agent — an end-to-end voice agent blueprint powered by NVIDIA Nemotron ASR, LLM, and TTS, designed for scalable, production-ready deployments.

### Added

- End-to-end voice agent pipeline with NVIDIA Nemotron ASR, LLM, and TTS, supporting streaming audio and mid-conversation interruptions
- Built on the open source [Pipecat-ai](https://github.com/pipecat-ai/pipecat) and [nvidia-pipecat](https://github.com/NVIDIA/voice-agent-examples) frameworks
- NVIDIA Nemotron Speech models:
  - [Parakeet CTC 1.1B](https://build.nvidia.com/nvidia/parakeet-ctc-1_1b-asr/modelcard) (English ASR)
  - [Parakeet 1.1B RNNT](https://build.nvidia.com/nvidia/parakeet-1_1b-rnnt-multilingual-asr/modelcard) (Multilingual ASR)
  - [Magpie TTS Multilingual](https://build.nvidia.com/nvidia/magpie-tts-multilingual/modelcard)
- NVIDIA Nemotron LLMs via NVIDIA NIM:
  - [Nemotron 3 Nano 30B A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard)
  - [Llama 3.3 Nemotron Super 49B v1.5](https://build.nvidia.com/nvidia/llama-3_3-nemotron-super-49b-v1_5/modelcard)
- WebRTC transport for real-time, low-latency voice communication with a custom frontend UI
- Docker Compose deployment with optional TURN server support for remote access
- Multilingual support with automatic language detection and seamless mid-conversation language switching
- Jetson Thor edge deployment support
- Pipeline customizations using environment variables and config files
  - ASR, LLM, TTS model change
  - Speculative speech processing enable/disable
  - Conversation history thresholds
  - output audio buffering
- Open telemetry tracing and monitoring support
- Documentation:
  - [Getting started guide](docs/01-getting-started.md) covering prerequisites, GPU configuration, and step-by-step setup
  - [Configuration guide](docs/02-configuration-guide.md) for pipeline customizations
  - [Jetson Thor deployment guide](docs/03-jetson-thor.md) for edge use cases
  - [Best practices guide](docs/04-best-practices.md) covering production deployment, latency optimization, and conversational UX
- AI agent deployment skill for Cursor and Claude Code to streamline deployment on workstations and Jetson Thor

### Known Issues

- ASR transcription can occasionally be inaccurate, though the LLM generally compensates by inferring meaning from context.
- The context aggregator limits chat history to 20 turns by default. Older turns are dropped when this limit is reached, rather than summarized.
