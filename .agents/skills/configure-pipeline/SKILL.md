---
name: configure-pipeline
description: Configure Nemotron Voice Agent runtime via `.env`, example-local `services.{cloud,local}.yaml`, and `prompt.yaml`. Use when changing prompts, tracing, S2S endpoint, audio knobs, or local NIM image overrides.
version: "1.0.0"
metadata:
  author: Ashutosh Rautela <arautela@nvidia.com>
  tags: [configuration, pipeline, voice-agent, nemotron]
---

# Configure Nemotron Voice Agent Pipeline

## Purpose

Edit the runtime configuration of the voice agent (built-in catalogs, prompts, feature flags) and re-apply Compose without rebuilding images.

## Prerequisites

- An existing deployment created by `deploy` (root compose or one of its per-example references).

## Scope

- Run commands from the repository root.
- Limit repository-backed changes to `.env`, `prompt.yaml`, and per-example service catalogs.
- UI-only prompt or service tests stay in browser localStorage. Redeployment is not required.
- Use `deploy` for initial deployment, profile selection, or auth troubleshooting.

## Instructions

1. Identify the active example by inspecting the running app container (`generic-example`, `agentic-airline-example`, or `all-examples`). Each example has its own catalog under `src/<family>/<example>/`.

2. Edit the smallest configuration surface that satisfies the request:
   - `.env`: feature flags, tracing, S2S settings, chat history, audio debugging, buffering, and local NIM image overrides such as `ASR_DOCKER_IMAGE`, `ASR_NIM_TAGS`, and `TTS_DOCKER_IMAGE`.
   - `<example-package>/services.cloud.yaml` (remote / NVCF) and `<example-package>/services.local.yaml` (Compose-managed local NIMs nested under `workstation` / `dgxspark` / `jetson`): built-in LLM, ASR, TTS, S2S, and example-specific role catalogs (e.g. `fast-llm`, `orchestrator-llm`, `booking-server`).
   - `prompt.yaml`: built-in prompt presets and prompt content.

3. Validate:
   - Multilingual prompts must use multilingual-capable ASR and TTS from the active catalog (e.g. `magpie-tts`, `parakeet-rnnt`); verify the keys exist before referencing them.
   - Local catalog endpoints must use Compose service names (`asr-service:50052`, `tts-service:50051`, `nvidia-llm:8000`, `nemotron-speech:50051`, `booking-server:8001`). Host-run backends auto-rewrite to the matching `localhost` ports.
   - ASR/TTS image overrides keep the same Compose service names and ports. For Parakeet CTC/RNNT ASR images, set `ASR_NIM_TAGS=mode=str,vad=silero`. Keep `mode=str` for Nemotron ASR. DGX Spark TTS image overrides keep `server: "tts-service:50051"`.
   - Workstation local Compose assumes 2 GPUs: ASR/TTS on GPU `0`, NIM LLM on GPU `1`.

4. Apply and verify using `references/apply-changes.md`.

## Rules

- Config-only changes use compose re-apply without `--build`.
- Preserve unrelated keys, comments, and entries while editing.
- Image-only local variants reuse `asr-service` / `tts-service`. Configure the image through `.env`.
- The first entry per catalog category is the runtime default; UI-side selection lives in browser localStorage.
- If only service catalog YAML or `prompt.yaml` changed, refresh the browser before concluding the update failed.

## Examples

**Switch the default LLM to a different cloud model:**

1. Open the active example's `services.cloud.yaml` and reorder so the target model is the first entry under `llm:` (or `fast-llm:` / `orchestrator-llm:` for Agentic Airline).
2. Refresh the browser; the catalog reloads without a container restart.

**Add a multilingual persona prompt:**

1. Add the new prompt to `prompt.yaml` (or set `PROMPT_SELECTOR=multilingual_voice_assistant`).
2. Make sure the active example's catalog has multilingual-capable ASR (`parakeet-rnnt`) and TTS (`magpie-tts`).
3. Re-apply the active profile because `.env` changed; refresh the browser after catalog or prompt changes.

## Limitations

- Does not deploy the stack or change profiles. Use `deploy` (and its per-example references) for that.
- Source code or `Dockerfile` changes require an image rebuild (`--build`); out of scope here.
- UI-only ad-hoc service / prompt overrides (saved in `localStorage`) are intentionally not persisted; this skill writes only to repo files.

## Troubleshooting

- **YAML catalog or `prompt.yaml` change does not appear in the UI** -> refresh the browser; built-in entries are cached. Re-apply Compose only if a startup default must be reloaded.
- **`.env` change has no effect on a running container** -> environment is read at container start. Re-apply Compose so the container restarts.
- **Local LLM/ASR/TTS missing from the Services tab** -> the corresponding sidecar is not deployed or is unreachable. The catalog filters local entries by TCP reachability.
- **Multilingual responses do not use the right ASR/TTS** -> reorder catalog so a multilingual ASR/TTS sits first, or pick the entry from the UI Services tab.
- **Local image override (`ASR_DOCKER_IMAGE` / `TTS_DOCKER_IMAGE`) image fails to pull** -> log in to `nvcr.io` with a `NVIDIA_API_KEY` that has access to the staging or private image.
