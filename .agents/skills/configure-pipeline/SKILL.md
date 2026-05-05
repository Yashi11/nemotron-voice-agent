---
name: configure-pipeline
description: Configure Nemotron Voice Agent runtime via `.env`, `services.{cloud,local}.yaml`, `prompt.yaml`. Use when changing defaults, prompts, tracing, or S2S.
version: "1.0.0"
metadata:
  author: Ashutosh Rautela <arautela@nvidia.com>
  tags: [configuration, pipeline, voice-agent, nemotron]
---

# Configure Nemotron Voice Agent Pipeline

## Purpose

Edit the runtime configuration of the voice agent (built-in catalogs, defaults, prompts, feature flags) and re-apply Compose without rebuilding images.

## Prerequisites

- An existing deployment created by `deploy` (root compose or one of its per-example references).
- Knowledge of the active deployment mode (cloud-only, workstation, dgxspark, or jetson) — infer from running services if unknown (see step 1).

## Scope

- Execute commands from the repository root.
- Limit repository-backed changes to `.env`, `prompt.yaml`, root service catalogs, and per-example service catalogs.
- UI-only prompt or service tests stay in browser localStorage. Redeployment is not required.
- Use `deploy` for initial deployment, hardware profile selection, or image and authentication troubleshooting.

## Instructions

1. Identify the current mode.
   - Use the specified deployment mode when it is already known.
   - Otherwise inspect running services:

   ```bash
   docker compose ps --services --status running
   ```

2. Infer the mode:
   - `nvidia-llm` running -> `workstation`
   - `nvidia-llm-vllm` with `asr-service` and `tts-service` running -> `dgxspark`
   - `nvidia-llm-vllm` without `asr-service` and `tts-service`, or Jetson platform markers detected (e.g., `nvidia-smi --query-gpu=name --format=csv,noheader` reports `NVIDIA Thor`, or `/proc/device-tree/model` exists) -> `jetson`
   - only an example service running with no NIM sidecars (one of `all-examples`, `generic-example`, or `agentic-airline-example`) -> `cloud-only`
   - `phoenix` may be present in any mode when tracing is enabled

3. Edit the smallest configuration surface that satisfies the request:
   - `.env`: defaults, feature flags, tracing, S2S settings, chat history, audio debugging, buffering, local NIM image overrides such as `ASR_DOCKER_IMAGE`, `ASR_NIM_TAGS`, and `TTS_DOCKER_IMAGE`
   - `services.cloud.yaml` (remote / NVCF) and `services.local.yaml` (on-prem when `DEPLOYMENT_PLATFORM` is set to `workstation`, `dgxspark`, or `jetson`): built-in LLM, ASR, TTS, and S2S catalog entries (see configure-services doc). Per-example catalogs at `src/cascaded/<example>/services.{cloud,local}.yaml` (e.g. `cascaded/generic/`, `cascaded/agentic_airline/`) are auto-selected when the server runs with `--bot cascaded.<example>.pipeline:bot`; edit those instead of the root catalogs in that case.
   - `prompt.yaml`: built-in prompt presets and prompt content

4. Validate:
   - if `.env` sets `DEFAULT_LLM`, `DEFAULT_ASR`, or `DEFAULT_TTS`, those keys should exist in the active service catalog. Otherwise, the first built-in entry in that category is used.
   - multilingual prompts must use multilingual-capable ASR and TTS from the active catalog. Use `magpie-tts` for TTS and `parakeet-rnnt` for ASR; verify the key exists before setting it.
   - local service entries must match the deployment-mode endpoint style
   - ASR/TTS image overrides keep the same Compose service names and ports. `services.local.yaml` changes are optional and only affect catalog labels or model metadata. For Parakeet CTC/RNNT ASR images, set `ASR_NIM_TAGS=mode=str,vad=silero`. Keep the default `mode=str` for Nemotron ASR. DGX Spark TTS image overrides keep `server: "tts-service:50051"`.
   - Workstation local Compose assumes 2 GPUs: ASR/TTS run on GPU `0`, and the NIM LLM runs on GPU `1`.

5. Apply and verify using `references/apply-changes.md`.

## Rules

- Config-only changes use compose re-apply without `--build`.
- Preserve unrelated keys, comments, and entries while editing.
- Image-only local variants reuse `asr-service` / `tts-service`. Configure the image through `.env`.
- If only service YAML catalogs or `prompt.yaml` changed, refresh the browser before concluding that the update failed.
- Confirm the deployment mode before applying changes when inference is ambiguous.

## Examples

**Switch the default LLM to a different cloud model (cloud-only mode):**

1. Open `services.cloud.yaml` and confirm the target model key exists under `llm:`.
2. In `.env`, set `DEFAULT_LLM=<target-key>`.
3. Re-apply the active profile using `references/apply-changes.md`.

**Add a multilingual persona prompt:**

1. Use `PROMPT_SELECTOR=multilingual_voice_assistant` or add a new multilingual prompt to `prompt.yaml`.
2. In `.env`, set `DEFAULT_TTS=magpie-tts` and `DEFAULT_ASR=parakeet-rnnt`.
3. If the active catalog has no multilingual ASR key, add one to that catalog before setting `DEFAULT_ASR`.
4. Re-apply the active profile because `.env` changed; refresh the browser after catalog or prompt changes.

## Limitations

- Does not deploy the stack or change profiles. Use `deploy` (and its per-example references) for that.
- Source code or `Dockerfile` changes require an image rebuild (`--build`); they are out of scope here.
- Browser-only ad-hoc service / prompt overrides (saved in `localStorage`) are intentionally not persisted; this skill writes only to repo files.

## Troubleshooting

- **YAML catalog or `prompt.yaml` change does not appear in the UI** -> refresh the browser; built-in entries are aggressively cached. Re-apply Compose only if a startup default must be reloaded.
- **`.env` change has no effect on a running container** -> environment is read at container start. Re-apply Compose so the container restarts.
- **`DEFAULT_LLM` / `DEFAULT_ASR` / `DEFAULT_TTS` falls back to the first catalog entry** -> the configured key does not exist in the active catalog (cloud or local). Add it to the catalog or correct the key.
- **Multilingual responses do not use the right ASR/TTS** -> ensure `DEFAULT_TTS=magpie-tts` and `DEFAULT_ASR` points to a multilingual ASR key in the active catalog.
- **Local image override (`ASR_DOCKER_IMAGE` / `TTS_DOCKER_IMAGE`) image fails to pull** -> log in to `nvcr.io` with a `NVIDIA_API_KEY` that has access to the staging or private image.
