# Generic - cascaded pipeline example

Generic cascaded voice pipeline using pipecat's built-in NVIDIA services
(`NvidiaSTTService` -> `NvidiaLLMService` with function calling ->
`NvidiaTTSService`). Use this example as the baseline cascaded reference
or as the starting point for your own use case.

Everything specific to the generic example lives under
`src/examples/generic/`: pipeline entry point, service catalogs, prompts,
and tool registrations. There is no per-example compose file because the
generic example has no example-specific sidecars. The app container and
shared sidecars are defined in the root `docker-compose.yml` and
`docker/` compose files.

## Overview and Use Cases

| Area | Details |
| --- | --- |
| Example intent | A minimal, production-shaped cascaded voice assistant that keeps ASR, LLM, tools, and TTS as separate services. |
| Architecture pattern | Use Pipecat's built-in NVIDIA service processors for speech recognition, function-calling chat completion, and speech synthesis. |
| What to study | Service catalog selection, prompt-scoped tool enablement, OpenAI-compatible function schemas, async tool handlers, and the import pattern for a new cascaded package. |
| Best fit | Teams that need a baseline voice-agent blueprint before adding domain logic, custom tools, or deployment-specific service choices. |
| Extend into | FAQ assistants, internal help desks, voice-controlled workflows, order capture, concierge bots, device control, or any use case where the conversation state can stay lightweight and tool calls are request/response oriented. |

## Layout

| Path | Role |
| --- | --- |
| `pipeline.py` | pipecat entry point for the generic example |
| `prompts.yaml` | example-local prompt catalog. Each entry may list `tools_available` to gate function calling per prompt |
| `tools.yaml` | OpenAI function-calling schemas, keyed by tool name |
| `tool_handlers.py` | async handlers for each schema in `tools.yaml`, exposed via the `TOOL_HANDLERS` registry |
| `tools.py` | builds a filtered `ToolsSchema` from `tools.yaml` for the tool names a prompt requests, skipping entries without a matching handler |
| `services.cloud.yaml`, `services.local.yaml` | example-local service catalogs; local ASR defaults to `nemotron-asr-streaming-english` |

## Running the example

Host-native (no Docker), set `selection: generic-assistant` in
[`examples_registry.yaml`](../../../examples_registry.yaml) at the repo root, then:

```bash
uv run python3 src/server.py
```

Docker — pick the recipe profile that matches your deployment intent.
Cloud-only:

```bash
docker compose --profile generic-assistant up -d
```

On-prem recipes layer the right LLM / ASR / TTS sidecars on top:

```bash
# Workstation (`nemotron-asr-streaming-english` + Magpie TTS + NIM LLM)
docker compose --profile generic-assistant/workstation up -d

# DGX Spark (`nemotron-asr-streaming-english` + Magpie TTS + vLLM LLM)
docker compose --profile generic-assistant/dgx-spark up -d

# Jetson Thor (vLLM LLM + Riva ASR + TTS via nemotron-speech)
docker compose --profile generic-assistant/jetson-thor up -d
```

Tear down with the same profile used at `up` time:

```bash
docker compose --profile generic-assistant/workstation down
```

| Recipe profile | App service | Sidecars |
| --- | --- | --- |
| `generic-assistant` | `generic-assistant` | none (cloud NVCF) |
| `generic-assistant/workstation` | `generic-assistant` | `nvidia-llm`, `nemotron-asr-streaming-english`, `tts-service` |
| `generic-assistant/dgx-spark` | `generic-assistant` | `nvidia-llm-vllm`, `nemotron-asr-streaming-english`, `tts-service` |
| `generic-assistant/jetson-thor` | `generic-assistant` | `nvidia-llm-vllm`, `nemotron-speech` |

The UI is served at `https://localhost:7860/` by default, or `http://localhost:7860/`
when `PIPELINE_TLS=false`.

The pipeline always uses this package's `services.cloud.yaml` and
`services.local.yaml` because the active example is resolved from
`examples_registry.yaml`.

## Import convention

Top-level `src/` is on `PYTHONPATH`, so imports should use:

```python
from examples.generic.pipeline import bot
```

and never `from src.examples.generic ...`.

## Agent skills

The repository ships AI agent skills under `skills/` that may help
with deployment and configuration:

| Skill | Purpose |
| --- | --- |
| [`deploy`](../../../skills/deploy/SKILL.md) | recipe-profile selection, NGC login, and root-compose deploy across supported example/hardware stacks |
| [`configure-pipeline`](../../../skills/configure-pipeline/SKILL.md) | edit `.env`, example-local `prompts.yaml`, or example-local `services.{cloud,local}.yaml`, then re-apply |

Install them into your coding agent with `npx skills add .` (see the
[top-level README](../../../README.md#agent-skills)).
