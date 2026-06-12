# Nemotron Omni Assistant Subagents - cascaded pipeline example

Multi-agent variant of [`omni-assistant`](../omni_assistant/README.md)
built on Pipecat's built-in multi-agent framework (`pipecat.workers`).
A transport agent owns I/O and TTS, a speaker agent owns spoken output,
and two worker agents handle uploaded media and live webcam vision.

Everything specific to this example lives under
`src/examples/omni_assistant_subagents/`: pipeline entry point,
per-agent modules, service catalogs, and prompts. There is no
per-example compose file. The app container and shared sidecars are
defined in the root and `docker/` compose files.

## Overview and Use Cases

| Area | Details |
| --- | --- |
| Example intent | A multimodal, multi-agent Omni assistant that keeps the voice conversation responsive while specialized agents analyze uploaded media and live webcam frames. |
| Architecture pattern | Split responsibility across a transport agent, speaker agent, media analyzer, and webcam agent using `pipecat.workers`, with explicit dispatch and acknowledgement points. |
| What to study | Agent boundaries, prompt separation, visual barge-in, deferred media dispatch, webcam scene summaries, and how UI capabilities are declared for attachments and webcam support. |
| Best fit | Teams building assistants that need spoken interaction plus asynchronous visual or media understanding without blocking the user-facing voice loop. |
| Extend into | Visual troubleshooting, field-service copilots, retail product assistance, inspection workflows, education and training tutors, accessibility helpers, or support agents that combine conversation with uploaded images, audio, video, or live camera context. |

## Layout

| Path | Role |
| --- | --- |
| `pipeline.py` | entry point that wires the four workers into a `WorkerRunner` over a shared `WorkerBus` |
| `subagents/speaker/agent.py` | `SpeakerOmniAgent` + structured-JSON wrapper around `NvidiaOmniMultimodalService` |
| `subagents/transport/agent.py` | `OmniTransportAgent` — transport I/O, TTS, visual barge-in, analyzer dispatch |
| `subagents/media_analyzer/agent.py` | `MediaAnalyzerWorker` for uploaded image / audio / video attachments |
| `subagents/webcam/agent.py` | `WebcamAgent` rolling scene summaries for live webcam context |
| `media_dispatch_processor.py` | frame-processor that defers analyzer dispatch until the speaker ack closes |
| `prompts.yaml` | example-local prompt catalog (top-level prompt + `agent_prompts:` per agent) |
| `services.cloud.yaml`, `services.local.yaml` | example-local service catalogs for cloud and on-prem deployments |

## Running the example

Host-native (no Docker), set `selection: omni-assistant-subagents`
in [`examples_registry.yaml`](../../../examples_registry.yaml) at the
repo root, then:

```bash
uv run python3 src/server.py
```

Docker — pick the recipe profile that matches your deployment intent.
Cloud-only:

```bash
docker compose --profile omni-assistant-subagents up -d
```

Workstation local Omni vLLM + NIM TTS:

```bash
docker compose --profile omni-assistant-subagents/workstation up -d
```

DGX Spark local Omni vLLM + NIM TTS:

```bash
docker compose --profile omni-assistant-subagents/dgx-spark up -d
```

Tear down with the same profile used at `up` time.

| Recipe profile | App service | Shared sidecars pulled from `docker/` |
| --- | --- | --- |
| `omni-assistant-subagents` | `omni-assistant-subagents` | none (cloud NVCF) |
| `omni-assistant-subagents/workstation` | `omni-assistant-subagents` | `nvidia-llm-vllm-omni`, `tts-service` |
| `omni-assistant-subagents/dgx-spark` | `omni-assistant-subagents` | `nvidia-llm-vllm-omni`, `tts-service` |

> Jetson is not supported today: the 30B Omni NVFP4 model does not fit on Orin-class hardware. A jetson recipe will be added once a smaller Omni variant lands.

The UI is served at `https://localhost:7860/` by default. Keep TLS enabled for
browser UI testing; `PIPELINE_TLS=false` is intended for headless performance
and API testing.

## Capabilities exposed to the UI

The example declares `capabilities: [attachments, webcam]` in
`examples_registry.yaml`, which gates these UI surfaces and backend
endpoints:

| Endpoint | Purpose |
| --- | --- |
| `POST /api/sessions/{session_id}/attachments?kind={image,audio,video}` | Upload media attachment for the media analyzer |
| `POST /api/sessions/{session_id}/webcam/frames` | Upload one webcam JPEG frame |
| `GET /api/webcam-config` | Browser webcam capture defaults |

## Import convention

Top-level `src/` is on `PYTHONPATH`, so imports should use:

```python
from examples.omni_assistant_subagents.pipeline import bot
```

and never `from src.examples.omni_assistant_subagents ...`.

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
[`deploy/references/omni-assistant-subagents-deploy.md`](../../../skills/deploy/references/omni-assistant-subagents-deploy.md)
for the subagents-specific profile combinations and failure modes.
