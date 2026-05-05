# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `nemotron-speech` compose service promotes Riva (ASR + TTS) to a first-class Jetson service so the full stack lifecycles via `docker compose --profile generic-jetson up -d`; replaces the prior host-side `riva_start.sh` flow
- CUDA MPS SM-split and disjoint CPU pinning for Thor's shared GPU and LPDDR5X bus: `VLLM_MPS_THREAD_PCT` / `RIVA_MPS_THREAD_PCT` and `VLLM_CPUSET` / `RIVA_CPUSET` / `PIPECAT_CPUSET`; `scripts/start-mps.sh` and `scripts/stop-mps.sh` manage the daemon
- Grouped service UI (Self-hosted / NVIDIA Cloud / Custom) in the LLM/ASR/TTS selectors, driven by namespaced service IDs returned by `/api/services`
- `APP_RUNTIME=container` marker set by `docker-compose.yml`; when absent the backend rewrites Compose-reachable endpoints in `services.local.yaml` to `localhost` so host-native runs (`uv run`) work without editing the catalog

### Changed

- Jetson ASR/TTS endpoint moves from `host.docker.internal:50051` to the `nemotron-speech:50051` compose service; host-run Pipecat rewrites it to `localhost:50051` automatically
- Service catalog split: `services.cloud.yaml` (remote / NVCF) and `services.local.yaml` (nested under `workstation` / `dgxspark` / `jetson`); the active catalog is selected from `DEPLOYMENT_PLATFORM`, and an unset/invalid `DEFAULT_LLM` / `DEFAULT_ASR` / `DEFAULT_TTS` falls back to the first entry in the active catalog
- S2S pipeline now authenticates with `NVIDIA_API_KEY` only; the former `S2S_API_KEY` env fallback (with OpenAI compatibility) has been removed

### Removed

- `LLM_INTERLEAVING` env flag and `NvidiaInterleavedLLMService`: MPS + CPU pinning replace the need for strict sentence-bounded interleaving
- `S2S_API_KEY` environment variable

## [2.0.0] - 2026-03-25

Major architecture upgrade: new Pipecat-based pipeline with speech-to-speech support, unified React client, and flexible deployment profiles.

### Added

- **Speech-to-speech pipeline mode** using Nemotron Voice Chat for direct voice-to-voice conversations
- **Cascaded pipeline mode** with separate ASR → LLM → TTS services, selectable from the UI
- Unified React/Vite client (`client/`) replacing the previous `frontend/` WebRTC and WebSocket UIs
- `services.yaml` service catalog for configuring LLM, ASR, TTS, and S2S endpoints
- `prompt.yaml` for persona/system prompt presets selectable from the UI
- Docker Compose profiles for flexible deployment:
  - `workstation`: 2 GPUs — ASR + TTS NIMs on GPU 0, NIM LLM on GPU 1
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
- `config/` directory (replaced by root-level `.env.example`, `services.yaml`, `prompt.yaml`)
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
