# Agentic Airline Cascaded Example — Deployment Reference

Use this reference from the `deploy` skill when deploying only the cascaded/agentic_airline example — a fast in-call LLM with state-runner orchestration for booking/rebook/cancel flows, alongside a SQLite-backed `booking-server` (port 8001).

## When to use

Deploying only the airline example, not the multi-example selector — use `--profile all-examples` from the root compose otherwise.

This example always brings up a `booking-server` alongside the voice pipeline. Booking flows fail silently if it is not healthy.

Available profiles: `agentic-airline` (cloud NVCF) and `agentic-airline-workstation` (local NIM ASR/TTS/LLM). No `dgxspark` or `jetson` variant exists.

Per-example catalogs at `src/cascaded/agentic_airline/services.{cloud,local}.yaml` are auto-selected on container startup and when Agentic Airline is the active UI example.

## Compose deploy

Cloud (NVCF):

```bash
docker compose --profile agentic-airline up -d
```

Workstation (local NIM ASR/TTS/LLM):

```bash
docker compose --profile agentic-airline-workstation up -d
```

Both profiles bring up `agentic-airline-example` + `booking-server`.

Tear down with the same profile. Add `-v` only when stale booking data must be dropped (clears the `booking_data` volume).

## Verify

- UI at `https://<host>:7860/`. Locked to airline; no example picker.
- Voice pipeline logs: `docker compose logs --tail 200 agentic-airline-example`.
- Booking backend logs: `docker compose logs --tail 200 booking-server`.
- Booking health: `curl -fk http://localhost:8001/health` from the host or `curl -f http://booking-server:8001/health` from inside the compose network.

## Common failures

- **Voice pipeline up but booking flows hang or return tool errors** -> `booking-server` is down. The voice pipeline does not crash when the backend is unreachable; it returns failed-tool responses. Check `booking-server` health.
- **`pull access denied` / `unauthorized`** -> NGC login was not done or expired. See the root `deploy` skill.
- **Stale booking data leaks across test runs** -> `docker compose down -v` drops the `booking_data` volume.
- **Tear-down leaves orphan services after a service rename** -> rerun `up` or `down` with `--remove-orphans`.
