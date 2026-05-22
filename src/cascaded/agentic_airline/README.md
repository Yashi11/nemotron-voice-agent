# Agentic Airline - cascaded pipeline example

Airline-focused cascaded voice pipeline with a fast in-call LLM plus a
state-runner orchestration layer for booking, rebooking, and
cancellation flows.

Everything specific to the airline example lives under
`src/cascaded/agentic_airline/`: pipeline entry point, service catalogs,
prompts, and the example-local compose file that ships the booking
backend sidecar.

## Layout

| Path | Role |
| --- | --- |
| `pipeline.py` | pipecat entry point for the airline example |
| `agent/` | fast-path router, bridge, and PNR context injection |
| `orchestrators/` | declarative state-runner flows for booking / rebook / cancel |
| `state/` | per-stream scratch memory and canonical entity store |
| `tools/` | fast-LLM tools plus booking-backend client |
| `booking_server/` | SQLite-backed booking backend — see [`booking_server/README.md`](booking_server/README.md) for the seeded PNRs, flight catalog, and worked example voice queries |
| `policy/` | deterministic fare / IRROPS policy tables |
| `prompts.yaml` | airline fast-agent prompt catalog |
| `services.cloud.yaml`, `services.local.yaml` | example-local service catalogs for cloud and on-prem deployments |
| `docker-compose.yml` | example-local booking-server sidecar, gated by the `cascaded/agentic-airline` profile |

## Running the example

Start the booking backend first when running directly on the host:

```bash
PYTHONPATH=src uv run python3 -m cascaded.agentic_airline.booking_server.server
```

Then start the voice server in another terminal. Set
`selection: cascaded/agentic-airline` in
[`examples_registry.yaml`](../../../examples_registry.yaml) at the repo
root first, then:

```bash
uv run python3 src/server.py
```

The booking client reads its base URL from the active service catalog
(`booking-server` entry). On host runs, the catalog rewrites
`http://booking-server:8001` to `http://localhost:8001` automatically.

Docker — pick the per-example profile, which activates both the app
variant and the booking-server sidecar:

```bash
docker compose --profile cascaded/agentic-airline up -d
```

Add a hardware profile to layer local NIM ASR / TTS / LLM sidecars on
top:

```bash
docker compose --profile cascaded/agentic-airline --profile workstation up -d
```

Tear down with the same profile combination used at `up` time:

```bash
docker compose --profile cascaded/agentic-airline --profile workstation down
```

| Profile combination | Services |
| --- | --- |
| `cascaded/agentic-airline` | `cascaded-agentic-airline` app + `booking-server` (cloud NVCF for ASR/LLM/TTS) |
| `cascaded/agentic-airline` + `workstation` | adds `nvidia-llm`, `asr-service`, `tts-service` from `cascaded/shared/` |

The UI is served at `https://localhost:7860/` by default, or `http://localhost:7860/`
when `PIPELINE_TLS=false`.

## Talking to the agent

The booking server seeds a fixed set of PNRs, flights, and routes. To
know which bookings to quote, which flight numbers to ask about, and
which voice queries the agent can actually fulfil against this data,
see [`booking_server/README.md`](booking_server/README.md) — it lists
the sample PNRs, the cities and date range covered, and worked example
prompts for every flow (lookup, status, rebook, cancel, book, standby,
route discovery, activity log).

## Import convention

Top-level `src/` is on `PYTHONPATH`, so imports should use:

```python
from cascaded.agentic_airline.pipeline import bot
```

and never `from src.cascaded.agentic_airline ...`.

## Agent skills

The repository ships AI agent skills under `.agents/skills/` that may help
with deployment and configuration:

| Skill | Purpose |
| --- | --- |
| [`deploy`](../../../.agents/skills/deploy/SKILL.md) | hardware-mode selection, NGC login, and root-compose deploy across every example × hardware profile combination |
| [`configure-pipeline`](../../../.agents/skills/configure-pipeline/SKILL.md) | edit `.env`, example-local prompts, or example-local `services.{cloud,local}.yaml`, then re-apply |

Install them into your coding agent with `npx skills add .` (see the
[top-level README](../../../README.md#agent-skills)). When deploying only
this example, the root `deploy` skill points at
[`deploy/references/agentic-airline-deploy.md`](../../../.agents/skills/deploy/references/agentic-airline-deploy.md)
for the airline-specific profile combinations, booking-server verification,
and example-specific failure modes.
