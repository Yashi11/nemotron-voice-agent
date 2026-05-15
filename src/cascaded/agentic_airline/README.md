# Agentic Airline - cascaded pipeline example

Airline-focused cascaded voice pipeline with a fast in-call LLM plus a
state-runner orchestration layer for booking, rebooking, and
cancellation flows.

This package follows the same example-style layout as
`src/cascaded/generic/`: everything specific to the airline example lives
under `src/cascaded/agentic_airline/`, including its pipeline entry point,
service catalogs, prompts, and example-local compose file.

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
| `services.cloud.yaml`, `services.local.yaml` | example-local service catalogs for standalone and selector runs |
| `docker-compose.yml` | example-local pipeline + booking backend stack |

## Running the example

Start the booking backend first when running directly on the host:

```bash
PYTHONPATH=src uv run python3 -m cascaded.agentic_airline.booking_server.server
```

Then start the voice server in another terminal:

```bash
uv run python3 src/server.py --bot cascaded.agentic_airline.pipeline:bot
```

The booking client reads its base URL from the active service catalog
(`booking-server` entry). On host runs, the catalog rewrites
`http://booking-server:8001` to `http://localhost:8001` automatically.

Or with the example-local compose files. The shared model services
(`nvidia-llm`, `asr-service`, `tts-service`) live in
`src/cascaded/shared/docker-compose.yml`, so any workstation run **must**
pass both compose files via `-f`.

Cloud (NVCF) — no shared services needed, only the airline compose:

```bash
docker compose \
  -f src/cascaded/agentic_airline/docker-compose.yml \
  --profile agentic-airline \
  up -d
```

Workstation (local NIM ASR / TTS / LLM) — stack the shared and airline
compose files:

```bash
docker compose \
  -f src/cascaded/shared/docker-compose.yml \
  -f src/cascaded/agentic_airline/docker-compose.yml \
  --profile agentic-airline-workstation \
  up -d
```

Tear down with the same `-f` flags as setup so compose can resolve every
service it brought up:

```bash
docker compose \
  -f src/cascaded/shared/docker-compose.yml \
  -f src/cascaded/agentic_airline/docker-compose.yml \
  --profile agentic-airline-workstation \
  down
```

The cloud profile starts `agentic-airline-example` + `booking-server`;
the workstation profile additionally brings up the shared `nvidia-llm`,
`asr-service`, and `tts-service` from `cascaded/shared/`. Either way, the
UI is served at `https://localhost:7860/` by default, or `http://localhost:7860/`
when `PIPELINE_TLS=false`. The app is locked to the airline example by its
`--bot cascaded.agentic_airline.pipeline:bot` startup command.

The compose path uses the multi-experience server selector. The package-local
`services.cloud.yaml` and `services.local.yaml` are selected automatically when
this example is active in the UI or launched with `--bot cascaded.agentic_airline.pipeline:bot`.

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
| [`deploy`](../../../.agents/skills/deploy/SKILL.md) | hardware-mode selection, NGC login, and root-compose deploy across every profile (`all-examples`, `generic[-*]`, `agentic-airline[-*]`) |
| [`configure-pipeline`](../../../.agents/skills/configure-pipeline/SKILL.md) | edit `.env`, example-local prompts, or example-local `services.{cloud,local}.yaml`, then re-apply |

Install them into your coding agent with `npx skills add .` (see the
[top-level README](../../../README.md#agent-skills)). When deploying only
this example (not the multi-example selector), the root `deploy` skill
points at
[`deploy/references/agentic-airline-deploy.md`](../../../.agents/skills/deploy/references/agentic-airline-deploy.md)
for the `agentic-airline[-workstation]` profile listing, booking-server
verification, and example-specific failure modes.
