# Thinker/Talker Cascaded Example

Independent cascaded voice example for the Thinker/Talker flight-booking design.

The Talker is the only user-facing LLM and exposes `call_thinker` plus
`cancel_thinker`.
The Thinker is session-local and owns flight search, selected-flight booking,
PNR status, lifecycle markers, and abort state. In the running pipeline it
talks to the booking-server sidecar in `airline/database` over HTTP as its
backend database; unit tests use a deterministic in-memory backend.

Booking is intentionally gated: the user must search flights first and select
one returned flight before the Thinker can continue booking.

Reusable Thinker/Talker architecture helpers live under `src/`. Airline
flight-booking domain logic lives under `airline/`. The root `pipeline.py`,
`prompts.yaml`, and service catalog files remain at the example root so the
example registry can resolve the bot, prompts, and default services from the
same directory.

## Running the example

Host-native (no Docker), set `selection: cascaded-thinker-talker/all` in
[`examples_registry.yaml`](../../../examples_registry.yaml) at the repo root.
Start the booking server in one shell:

```bash
PYTHONPATH=src uv run python3 -m cascaded.thinker_talker.airline.database.server
```

Then start the UI server in another shell:

```bash
uv run python3 src/server.py
```

Docker - pick the recipe profile that matches your deployment intent.
Cloud ASR, LLM, and TTS with the local booking-server sidecar:

```bash
docker compose --profile cascaded-thinker-talker up -d
```

Workstation local NIM ASR, TTS, and Talker/Thinker LLM with the local
booking-server sidecar:

```bash
docker compose --profile cascaded-thinker-talker/workstation up -d
```

Tear down with the same profile used at `up` time.

| Recipe profile | App service | Sidecars |
| --- | --- | --- |
| `cascaded-thinker-talker` | `cascaded-thinker-talker` | `booking-server` |
| `cascaded-thinker-talker/workstation` | `cascaded-thinker-talker` | `booking-server`, `nvidia-llm`, `asr-service`, `tts-service` |

The UI is served at `https://localhost:7860/` by default, or
`http://localhost:7860/` when `PIPELINE_TLS=false`.

## Tunables

| Env var | Default | Purpose |
| --- | --- | --- |
| `CHAT_HISTORY_RECENT_TURNS` | `20` | Number of recent non-prompt messages retained in the Talker context window |
| `THINKER_FILLER_THRESHOLD_SECONDS` | `0.3` | Delay before optional `call_thinker.filler_text` is spoken while Thinker work is still running |
| `THINKER_TOOL_TIMEOUT_SECONDS` | `30.0` | Timeout for `call_thinker` / `cancel_thinker` tool handlers |

## Import convention

Top-level `src/` is on `PYTHONPATH`, so imports should use:

```python
from cascaded.thinker_talker.pipeline import bot
```

and never `from src.cascaded.thinker_talker ...`.
