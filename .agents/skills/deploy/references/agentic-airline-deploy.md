# Agentic Airline Cascaded Example — Deployment Reference

Use this reference from the `deploy` skill when deploying the cascaded/agentic_airline example — a fast in-call LLM with state-runner orchestration for booking/rebook/cancel flows, alongside a SQLite-backed `booking-server` (port 8001).

## When to use

Pinning a Docker Compose deployment to the Agentic Airline example. Recipe profile names encode both the example and the hardware target. Selector modes (`cascaded/all`, `all`) are host-native only — they are not exposed as compose profiles.

This example always brings up `booking-server` alongside the voice pipeline — both are gated by the active recipe. Booking flows fail silently if the backend is not healthy.

Hardware support: cloud-only and `workstation`. There is no `dgxspark` or `jetson` recipe for this example.

Per-example catalogs at `src/cascaded/agentic_airline/services.{cloud,local}.yaml` are auto-selected on container startup because the registry resolves the example for the active recipe.

## Compose deploy

```bash
# Cloud (NVCF)
docker compose --profile cascaded/agentic-airline up -d

# Workstation (local NIM ASR/TTS/LLM)
docker compose --profile cascaded/agentic-airline/workstation up -d
```

Either recipe brings up `cascaded-agentic-airline` + `booking-server`. The workstation recipe additionally brings up `nvidia-llm`, `asr-service`, `tts-service` from `cascaded/shared/`.

Tear down with the same recipe. Add `-v` only when stale booking data must be dropped (clears the `booking_data` volume).

## Verify

- UI at `https://<host>:7860/` by default, or `http://<host>:7860/` when `PIPELINE_TLS=false`.
- Voice pipeline logs: `docker compose logs --tail 200 cascaded-agentic-airline`.
- Booking backend logs: `docker compose logs --tail 200 booking-server`.
- Booking health: `curl -fk http://localhost:8001/health` from the host or `curl -f http://booking-server:8001/health` from inside the compose network.

## Common failures

- **Voice pipeline up but booking flows hang or return tool errors** -> `booking-server` is down. The voice pipeline does not crash when the backend is unreachable. It returns failed-tool responses. Check `booking-server` health.
- **`pull access denied` / `unauthorized`** -> NGC login was not done or expired. See the root `deploy` skill.
- **Stale booking data leaks across test runs** -> `docker compose --profile cascaded/agentic-airline down -v` drops the `booking_data` volume.
- **Tear-down leaves orphan services after a service rename** -> rerun `up` or `down` with `--remove-orphans`.
