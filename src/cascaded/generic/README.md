# Generic - cascaded pipeline example

Generic cascaded voice pipeline using pipecat's built-in NVIDIA services
(`NvidiaSTTService` -> `NvidiaLLMService` with function calling ->
`NvidiaTTSService`). Use this example as the baseline cascaded reference
or as the starting point for your own use case.

Everything specific to the generic example lives under
`src/cascaded/generic/`: pipeline entry point, service catalogs, prompts,
and tool registrations. There is no per-example compose file because the
generic example has no example-specific sidecars; the app container and
shared sidecars are defined in the root and `cascaded/shared/`
compose files.

## Layout

| Path | Role |
| --- | --- |
| `pipeline.py` | pipecat entry point for the generic example |
| `prompts.yaml` | example-local prompt catalog; each entry may list `tools_available` to gate function calling per prompt |
| `tools.yaml` | OpenAI function-calling schemas, keyed by tool name |
| `tool_handlers.py` | async handlers for each schema in `tools.yaml`, exposed via the `TOOL_HANDLERS` registry |
| `tools.py` | builds a filtered `ToolsSchema` from `tools.yaml` for the tool names a prompt requests, skipping entries without a matching handler |
| `services.cloud.yaml`, `services.local.yaml` | example-local service catalogs for cloud and on-prem deployments |

## Running the example

Host-native (no Docker), set `selection: cascaded/generic` in
[`examples_registry.yaml`](../../../examples_registry.yaml) at the repo root, then:

```bash
uv run python3 src/server.py
```

Docker — pick the per-example profile (cloud-only):

```bash
docker compose --profile cascaded/generic up -d
```

Add a hardware profile to layer local NIM / vLLM / Riva sidecars on top:

```bash
# Workstation (local NIM ASR / TTS / LLM)
docker compose --profile cascaded/generic --profile workstation up -d

# DGX Spark (vLLM LLM + NIM ASR / TTS)
docker compose --profile cascaded/generic --profile dgxspark up -d

# Jetson (vLLM LLM + Riva ASR + TTS via nemotron-speech)
docker compose --profile cascaded/generic --profile jetson up -d
```

Tear down with the same profile combination used at `up` time:

```bash
docker compose --profile cascaded/generic --profile workstation down
```

| Profile combination | App service | Shared sidecars pulled from `cascaded/shared/` |
| --- | --- | --- |
| `cascaded/generic` | `cascaded-generic` | none (cloud NVCF) |
| `cascaded/generic` + `workstation` | `cascaded-generic` | `nvidia-llm`, `asr-service`, `tts-service` |
| `cascaded/generic` + `dgxspark` | `cascaded-generic` | `nvidia-llm-vllm`, `asr-service`, `tts-service` |
| `cascaded/generic` + `jetson` | `cascaded-generic` | `nvidia-llm-vllm`, `nemotron-speech` |

The UI is served at `https://localhost:7860/` by default, or `http://localhost:7860/`
when `PIPELINE_TLS=false`.

The pipeline always uses this package's `services.cloud.yaml` and
`services.local.yaml` because the active example is resolved from
`examples_registry.yaml`.

## Import convention

Top-level `src/` is on `PYTHONPATH`, so imports should use:

```python
from cascaded.generic.pipeline import bot
```

and never `from src.cascaded.generic ...`.

## Agent skills

The repository ships AI agent skills under `.agents/skills/` that may help
with deployment and configuration:

| Skill | Purpose |
| --- | --- |
| [`deploy`](../../../.agents/skills/deploy/SKILL.md) | hardware-mode selection, NGC login, and root-compose deploy across every example / hardware profile combination |
| [`configure-pipeline`](../../../.agents/skills/configure-pipeline/SKILL.md) | edit `.env`, example-local `prompts.yaml`, or example-local `services.{cloud,local}.yaml`, then re-apply |

Install them into your coding agent with `npx skills add .` (see the
[top-level README](../../../README.md#agent-skills)).
