# Thinker/Talker Deploy Reference

Use this reference from the `deploy` skill when deploying the cascaded Thinker/Talker airline assistant.

## Profiles

Pin Docker Compose to one Thinker/Talker recipe. The cloud recipe uses NVIDIA cloud ASR, Talker LLM, Thinker LLM, and TTS, plus the local booking-server sidecar. The workstation recipe runs local NIM ASR, TTS, and a shared Talker/Thinker LLM, plus the local booking-server sidecar.

```bash
docker compose --profile thinker-talker up -d
docker compose --profile thinker-talker/workstation up -d
```

| Recipe profile | App service | Sidecars |
| --- | --- | --- |
| `thinker-talker` | `thinker-talker` | `booking-server` |
| `thinker-talker/workstation` | `thinker-talker` | `booking-server`, `nvidia-llm`, `nemotron-asr-streaming-english`, `tts-service` |

Tear down with the same recipe used at `up` time.

```bash
docker compose --profile <recipe> down
```

## Verify

- App logs: `docker compose logs --tail 200 thinker-talker`.
- Booking server logs: `docker compose logs --tail 200 booking-server`.
- Workstation local service logs: `docker compose logs --tail 200 nvidia-llm nemotron-asr-streaming-english tts-service`.

## Limits

Thinker/Talker currently supports cloud-only and workstation recipes. Do not use DGX Spark or Jetson Thor profile names for this example unless matching compose recipes are added first.
