# Frontend/Backend Agent Cascaded Example

Independent cascaded voice example for the Frontend/Backend Agent flight-booking design.

The frontend LLM is the only user-facing LLM and exposes `call_backend` plus
`cancel_backend` as internal delegation tools.
The backend agent is scoped to each conversation and owns flight search,
selected-flight booking, PNR status, lifecycle markers, and abort state. In
the running pipeline it talks to the booking-server sidecar in
`airline/database` over HTTP as its backend database; unit tests use a
deterministic in-memory backend.

The airline backend agent is the reference backend for this example, but the
architecture is intended to be reusable: the frontend LLM can act as a generic
conversational layer in front of another backend agent.

Booking is intentionally gated: the user must search flights first and select
one returned flight before the backend agent can continue booking.

Reusable Frontend/Backend Agent architecture helpers live under `src/`. Airline
flight-booking domain logic lives under `airline/`. The root `pipeline.py`,
`prompts.yaml`, and service catalog files remain at the example root so the
example registry can resolve the bot, prompts, and default services from the
same directory.

## Overview and Use Cases

| Area | Details |
| --- | --- |
| Example intent | A stateful airline support agent that separates fast user-facing speech from slower planning and tool work for flight search, booking, PNR status, rebooking, cancellation, and standby flows. |
| Architecture pattern | Use a frontend LLM for the live conversation and a backend agent scoped to that conversation for durable domain state, policy checks, backend calls, lifecycle markers, and abort handling. |
| Reusability model | Treat the frontend LLM as a generic conversational layer. The bundled airline backend agent can be replaced with another agentic architecture when that backend exposes compatible call/cancel behavior and returns speech-ready progress or results. |
| What to study | `call_backend` and `cancel_backend` tool contracts, booking-server integration, selected-flight gating, per-conversation backend state, and how filler speech keeps the voice loop responsive during longer work. |
| Best fit | Teams building transactional agents where correctness, state transitions, policy enforcement, and interrupt handling matter more than a single-turn answer. |
| Extend into | Travel servicing, appointment scheduling, insurance claims, returns and exchanges, subscription management, banking-style service flows, or any workflow that needs a responsive front-channel assistant backed by a deliberative task agent. |

## Architecture

![Frontend/Backend Agent architecture](images/frontend-backend-agent-architecture.png)

## Best Practices

The diagram shows the full runtime path: user audio enters through the
WebRTC/WebSocket transport, audio input processing produces a user transcript
for the frontend LLM, the frontend LLM sends rephrased task requirements to the
backend agent, and backend results return to the frontend LLM before audio
output is synthesized and played back.

### Preserve the frontend/backend split

The frontend LLM is the only user-facing component. For flight-task turns, it
should call `call_backend` or `cancel_backend` with empty spoken content. It
should not ask booking-specific missing-field questions, summarize pending
flight work, expose tools, or mention internal architecture.

The backend agent owns domain planning, slot extraction, backend calls, booking
state, policy checks, and final task responses.

### Send self-contained backend requests

Each `call_backend` query should describe the complete current request using
the latest user turn plus relevant prior context. Avoid delta-only requests
like "change the previous booking." The latest correction should override older
context.

### Treat cancellation as a required path

Use `cancel_backend` when the user says to stop, cancel, abandon, ignore, or
never mind pending flight work. Also use it when the user switches to unrelated
small talk or a non-flight topic while flight work may still be pending. This
prevents stale backend results from reaching the user later.

### Re-test tool-calling accuracy after prompt changes

Prompt edits can silently break the architecture contract. After changing the
frontend or backend prompts, test both routing layers:

- Frontend LLM calls `call_backend` for flight search, booking continuation, flight
  selection, passenger details, seat or meal preferences, confirmations,
  corrections, and PNR-status requests.
- Frontend LLM calls `cancel_backend` for stop, cancel, never-mind requests, and
  topic switches while flight work is pending.
- Frontend LLM does not call tools for greetings, thanks, or small talk when no
  flight task is pending.
- Backend agent calls `flight_search` only when required route and date details are
  available.
- Backend agent calls `booking` only after a searched flight has been selected.
- Backend agent calls `pnr_status` for PNR, record-locator, or booking-status
  requests.
- Backend agent returns `response_hint` for missing information or unsupported
  requests instead of inventing backend results.

### Keep internal protocol private and speech clean

Lifecycle markers, raw tool JSON, backend names, and implementation details are
internal only. User-facing speech should come from explicit `response_text`
fields in `response_hint` or `tool_result`, with TTS-ready wording.

## Running the example

Host-native (no Docker), set `selection: frontend-backend-agent` in
[`examples_registry.yaml`](../../../examples_registry.yaml) at the repo root.
Start the booking server in one shell:

```bash
PYTHONPATH=src uv run python3 -m examples.frontend_backend_agent.airline.database.server
```

Then start the UI server in another shell:

```bash
uv run python3 src/server.py
```

Docker - pick the recipe profile that matches your deployment intent.
Cloud ASR, LLM, and TTS with the local booking-server sidecar:

```bash
docker compose --profile frontend-backend-agent up -d
```

Workstation local NIM ASR, TTS, and frontend/backend LLM with the local
booking-server sidecar:

```bash
docker compose --profile frontend-backend-agent/workstation up -d
```

Tear down with the same profile used at `up` time.

| Recipe profile | App service | Sidecars |
| --- | --- | --- |
| `frontend-backend-agent` | `frontend-backend-agent` | `booking-server` |
| `frontend-backend-agent/workstation` | `frontend-backend-agent` | `booking-server`, `nvidia-llm`, `nemotron-asr-streaming-english`, `tts-service` |

The UI is served at `https://localhost:7860/` by default. Keep TLS enabled for
browser UI testing; `PIPELINE_TLS=false` is intended for headless performance
and API testing. If you still need HTTP for temporary browser testing, open the
browser flags page (for example,
`chrome://flags/#unsafely-treat-insecure-origin-as-secure` in Chrome or
`edge://flags/#unsafely-treat-insecure-origin-as-secure` in Edge), enable the
`Insecure origins treated as secure` flag, add `http://localhost:7860`,
relaunch the browser, and remove the origin after testing.

## Tunables

The `THINKER_*` environment variable names are legacy runtime names retained
for compatibility with existing deployments; they still configure backend-agent
tool behavior in this example.

| Env var | Default | Purpose |
| --- | --- | --- |
| `CHAT_HISTORY_RECENT_TURNS` | `20` | Number of recent non-prompt messages retained in the frontend LLM context window |
| `THINKER_FILLER_THRESHOLD_SECONDS` | `0.3` | Delay before optional `call_backend.filler_text` is spoken while backend work is still running |
| `THINKER_TOOL_TIMEOUT_SECONDS` | `30.0` | Timeout for `call_backend` / `cancel_backend` tool handlers |

## Import convention

Top-level `src/` is on `PYTHONPATH`, so imports should use:

```python
from examples.frontend_backend_agent.pipeline import bot
```

and never `from src.examples.frontend_backend_agent ...`.
