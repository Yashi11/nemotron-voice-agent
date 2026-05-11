# Generic - cascaded pipeline example

Generic cascaded voice pipeline using pipecat's built-in NVIDIA services
(`NvidiaSTTService` -> `NvidiaLLMService` with function calling ->
`NvidiaTTSService`). Use this example as the baseline cascaded reference
or as the starting point for your own use case.

This package follows the same example-style layout as
`src/cascaded/agentic_airline/`: everything specific to the generic
example lives under `src/cascaded/generic/`, including its pipeline
entry point, service catalogs, and example-local compose file.

## Layout

| Path | Role |
| --- | --- |
| `pipeline.py` | pipecat entry point for the generic example |
| `prompts.yaml` | example-local prompt catalog; each entry may list `tools_available` to gate function calling per prompt |
| `tools.yaml` | OpenAI function-calling schemas, keyed by tool name |
| `tool_handlers.py` | async handlers for each schema in `tools.yaml`, exposed via the `TOOL_HANDLERS` registry |
| `tools.py` | builds a filtered `ToolsSchema` from `tools.yaml` for the tool names a prompt requests, skipping entries without a matching handler |
| `services.cloud.yaml`, `services.local.yaml` | example-local service catalogs for standalone and selector runs |
| `docker-compose.yml` | example-local pipeline app stack (pairs with `cascaded/shared/`) |

## Running the example

Start the voice server directly on the host:

```bash
uv run python3 src/server.py --bot cascaded.generic.pipeline:bot
```

Or with the example-local compose files. The shared model services
(`nvidia-llm`, `nvidia-llm-vllm`, `asr-service`, `tts-service`,
`nemotron-speech`) live in `src/cascaded/shared/docker-compose.yml`, so
any non-cloud run **must** pass both compose files via `-f` — running
the generic compose alone will fail with `service
"generic-example-workstation" depends on undefined service
"asr-service"` (or the equivalent for whichever platform profile you
selected).

Cloud (NVCF) — no shared services needed, only the generic compose:

```bash
docker compose \
  -f src/cascaded/generic/docker-compose.yml \
  --profile generic \
  up -d
```

Workstation (local NIM ASR / TTS / LLM) — stack the shared and generic
compose files:

```bash
docker compose \
  -f src/cascaded/shared/docker-compose.yml \
  -f src/cascaded/generic/docker-compose.yml \
  --profile generic-workstation \
  up -d
```

DGX Spark (vLLM LLM + NIM ASR / TTS):

```bash
docker compose \
  -f src/cascaded/shared/docker-compose.yml \
  -f src/cascaded/generic/docker-compose.yml \
  --profile generic-dgxspark \
  up -d
```

Jetson (vLLM LLM + Riva ASR + TTS via `nemotron-speech`):

```bash
docker compose \
  -f src/cascaded/shared/docker-compose.yml \
  -f src/cascaded/generic/docker-compose.yml \
  --profile generic-jetson \
  up -d
```

Tear down with the same `-f` flags as setup so compose can resolve every
service it brought up:

```bash
docker compose \
  -f src/cascaded/shared/docker-compose.yml \
  -f src/cascaded/generic/docker-compose.yml \
  --profile generic-workstation \
  down
```

(Swap the profile to match the one used at `up` time.)

| Profile | Pipeline app | Shared backends pulled from `cascaded/shared/` |
| --- | --- | --- |
| `generic` | `generic-example` | none (cloud NVCF) |
| `generic-workstation` | `generic-example` | `nvidia-llm`, `asr-service`, `tts-service` |
| `generic-dgxspark` | `generic-example` | `nvidia-llm-vllm`, `asr-service`, `tts-service` |
| `generic-jetson` | `generic-example` | `nvidia-llm-vllm`, `nemotron-speech` |

The UI is served at `https://localhost:7860/`. In the UI, select
**Cascaded → Generic** before connecting.

The compose path uses the multi-experience server selector. The package-local
`services.cloud.yaml` and `services.local.yaml` are selected automatically when
this example is active in the UI or launched with `--bot cascaded.generic.pipeline:bot`.

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
| [`deploy`](../../../.agents/skills/deploy/SKILL.md) | hardware-mode selection, NGC login, and root-compose deploy across every profile (`all-examples`, `generic[-*]`, `agentic-airline[-*]`) |
| [`configure-pipeline`](../../../.agents/skills/configure-pipeline/SKILL.md) | edit `.env`, example-local `prompts.yaml`, or example-local `services.{cloud,local}.yaml`, then re-apply |

Install them into your coding agent with `npx skills add .` (see the
[top-level README](../../../README.md#agent-skills)). When deploying only
this example (not the multi-example selector), the root `deploy` skill
points at
[`deploy/references/generic-deploy.md`](../../../.agents/skills/deploy/references/generic-deploy.md)
for the `generic[-*]` profile listing and example-specific verification.
