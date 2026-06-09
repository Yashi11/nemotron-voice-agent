# Nemotron Omni Assistant - cascaded pipeline example

Cascaded voice pipeline that uses Nemotron 3 Nano Omni as a single
audio-input model for ASR and LLM, then hands the text reply to Magpie
TTS. This example enables only text/audio inputs. Uploaded media and webcam
vision are covered by `cascaded-omni`.

Everything specific to this example lives under
`src/cascaded/omni_assistant/`: pipeline entry point, the Omni
multimodal service, service catalogs, and prompts. There is no
per-example compose file. The app container and shared sidecars are
defined in the root and `docker/` compose files.

## Overview and Use Cases

| Area | Details |
| --- | --- |
| Example intent | A cascaded Omni voice assistant where Nemotron Omni consumes user audio directly and produces the assistant text that Magpie TTS speaks. |
| Architecture pattern | Replace the separate ASR and text LLM stages with one audio-input LLM service while preserving the familiar Pipecat transport, TTS, prompt, and service-catalog flow. |
| What to study | `NvidiaOmniMultimodalService`, audio-only turn finalization, transcript recovery from Omni responses, and the smaller service surface needed for an Omni-based assistant. |
| Best fit | Teams evaluating whether an audio-input LLM can simplify a voice stack or improve handling of spoken context before adding heavier domain workflows. |
| Extend into | General conversational assistants, voice-first copilots, meeting or note-taking helpers, hands-free product guides, training companions, or domain agents that benefit from direct acoustic context with conventional TTS output. |

## Layout

| Path | Role |
| --- | --- |
| `pipeline.py` | pipecat entry point for the Omni Assistant example |
| `nvidia_omni_multimodal_service.py` | `NvidiaOmniMultimodalService` (upstream-shaped Pipecat `LLMService` for Nemotron Omni) |
| `audio_only_smart_turn_strategy.py` | smart-turn stop strategy that finalizes turns without an upstream `TranscriptionFrame` |
| `prompts.yaml` | example-local prompt catalog |
| `services.cloud.yaml`, `services.local.yaml` | example-local service catalogs for cloud and on-prem deployments |

## Running the example

Host-native (no Docker), set `selection: cascaded-omni` in
[`examples_registry.yaml`](../../../examples_registry.yaml) at the repo
root, then:

```bash
uv run python3 src/server.py
```

Docker — pick the recipe profile that matches your deployment intent.
Cloud-only:

```bash
docker compose --profile cascaded-omni up -d
```

Workstation or DGX Spark (local Omni vLLM + NIM TTS):

```bash
docker compose --profile cascaded-omni/workstation up -d
docker compose --profile cascaded-omni/dgx-spark up -d
```

Tear down with the same profile used at `up` time.

| Recipe profile | App service | Shared sidecars pulled from `docker/` |
| --- | --- | --- |
| `cascaded-omni` | `cascaded-omni` | none (cloud NVCF) |
| `cascaded-omni/workstation` | `cascaded-omni` | `nvidia-llm-vllm-omni`, `tts-service` |
| `cascaded-omni/dgx-spark` | `cascaded-omni` | `nvidia-llm-vllm-omni`, `tts-service` |

> Jetson is not supported today: the 30B Omni NVFP4 model does not fit on Orin-class hardware. A jetson recipe will be added once a smaller Omni variant lands.

The UI is served at `https://localhost:7860/` by default, or `http://localhost:7860/`
when `PIPELINE_TLS=false`.

## Tunables

Environment variables read by [`pipeline.py`](pipeline.py):

| Env var | Default | Purpose |
| --- | --- | --- |
| `OMNI_MAX_TOKENS` | `8192` | Max tokens for the Omni response |
| `OMNI_TEMPERATURE` | `0.6` | Sampling temperature |
| `OMNI_TOP_P` | `0.95` | Nucleus sampling top-p |
| `OMNI_MIN_USER_AUDIO_SECS` | `0.3` | Drop turns shorter than this |
| `OMNI_EMIT_TRANSCRIPTIONS` | `true` | Parse `{"transcript", "response"}` from the Omni response so the user transcript is recovered |
| `TTS_STOP_FRAME_TIMEOUT_S` | `30` | TTS audio-context idle timeout |
| `AUDIO_OUT_10MS_CHUNKS` | `5` (WebRTC) / `10` (WebSocket) | Outbound audio framing |

## Import convention

Top-level `src/` is on `PYTHONPATH`, so imports should use:

```python
from cascaded.omni_assistant.pipeline import bot
```

and never `from src.cascaded.omni_assistant ...`.

## Agent skills

The repository ships AI agent skills under `skills/` that may help
with deployment and configuration:

| Skill | Purpose |
| --- | --- |
| [`deploy`](../../../skills/deploy/SKILL.md) | recipe-profile selection, NGC login, and root-compose deploy across supported example/hardware stacks |
| [`configure-pipeline`](../../../skills/configure-pipeline/SKILL.md) | edit `.env`, example-local `prompts.yaml`, or example-local `services.{cloud,local}.yaml`, then re-apply |

Install them into your coding agent with `npx skills add .` (see the
[top-level README](../../../README.md#agent-skills)). When deploying only
this example, the root `deploy` skill points at
[`deploy/references/omni-assistant-deploy.md`](../../../skills/deploy/references/omni-assistant-deploy.md)
for the Omni-specific profile combinations and failure modes.
