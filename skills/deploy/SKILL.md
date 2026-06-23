---
name: deploy
description: Deploy Nemotron Voice Agent via root compose using recipe profiles. Use when deploying or troubleshooting auth/startup.
version: "1.0.0"
metadata:
  author: Ashutosh Rautela <arautela@nvidia.com>
  tags: [deployment, docker-compose, voice-agent, nemotron]
---

# Nemotron Voice Agent Deployment

## Rules

- Run commands from the repository root containing `docker-compose.yml`.
- Use Docker Compose for deployment.
- Preserve existing `.env`. Create it only if missing.
- Use `configure-pipeline` for `.env`, catalog, or prompt changes.
- Every deployment specifies **exactly one recipe profile** (plus optional observability profiles). `docker compose up` with no profile is a no-op.
- Recipe profile names are `<example>` for cloud-only deployments and `<example>/<hardware>` for on-prem deployments (for example `generic-assistant` and `generic-assistant/workstation`). The profile is a complete, self-contained recipe — never combine two recipes.
- Selector modes (`all`, or a single `<example>` such as `generic-assistant`) remain host-native only (`uv run`) and have no compose profile.
- Observability profiles (`tracing`, `turn`) compose orthogonally with any recipe.
- When adding the `turn` profile, complete the TURN preflight before `docker compose up`: confirm bundled coturn is supported on the host architecture, ensure `.env` has `TURN_USERNAME` and `TURN_PASSWORD`, set `TURN_URL` when TURN is hosted separately or the request host is not client-reachable, and remind the user to open UDP `3478` and `49160-49200`.

## Deploy

1. Check hardware:

```bash
cat /sys/class/dmi/id/product_name 2>/dev/null || true
cat /proc/device-tree/model 2>/dev/null || true
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader
free -h
```

2. Identify the hardware target:
- `jetson`: `/proc/device-tree/model` identifies a Jetson platform, or the GPU name is `NVIDIA Thor`.
- `dgxspark`: `/sys/class/dmi/id/product_name` contains `DGX Spark` or `DGX_Spark` case-insensitively.
- `workstation`: non-DGX Spark, non-Jetson host with enough GPU VRAM for the selected local NIM services. Single-GPU hosts are valid when capacity is sufficient.
- _(omit hardware)_: local platform requirements are not met, or remote/NVCF services are preferred (cloud-only).

3. Prepare `.env`:

```bash
test -f .env || cp .env.example .env
```

Required keys: `NVIDIA_API_KEY` for all recipes. `HF_TOKEN` for any recipe that ends in `/dgx-spark` or `/jetson-thor`, plus `omni-assistant/workstation` and `omni-assistant-subagents/workstation`. `TURN_USERNAME` and `TURN_PASSWORD` are required when adding `--profile turn`.

4. Pick the recipe profile:

| Goal | Recipe profile |
| --- | --- |
| Cloud-only Generic Cascaded | `generic-assistant` |
| Cloud-only Multilingual Cascaded | `multilingual-assistant` |
| Cloud-only Omni Assistant | `omni-assistant` |
| Cloud-only Omni Assistant Subagents | `omni-assistant-subagents` |
| Cloud-only Thinker/Talker Airline Assistant | `thinker-talker` |
| Generic Cascaded on a workstation | `generic-assistant/workstation` |
| Generic Cascaded on DGX Spark | `generic-assistant/dgx-spark` |
| Generic Cascaded on Jetson Thor | `generic-assistant/jetson-thor` |
| Multilingual Cascaded on a workstation | `multilingual-assistant/workstation` |
| Multilingual Cascaded on DGX Spark | `multilingual-assistant/dgx-spark` |
| Omni Assistant on a workstation | `omni-assistant/workstation` |
| Omni Assistant on DGX Spark | `omni-assistant/dgx-spark` |
| Omni Assistant on Jetson Thor | `omni-assistant/jetson-thor` |
| Omni Assistant Subagents on DGX Spark | `omni-assistant-subagents/dgx-spark` |
| Thinker/Talker Airline Assistant on a workstation | `thinker-talker/workstation` |


For any on-prem recipe, log in to `nvcr.io` first.

5. Start:

```bash
docker compose --profile <recipe> up -d
```

Add observability profiles freely: `--profile tracing` (Phoenix), `--profile turn` (coturn). Before adding `--profile turn`, follow `references/platform-deployment.md#turn` to populate TURN credentials and any required `TURN_URL`. Use `--build` only after source or `Dockerfile` changes.

6. Verify:

```bash
docker compose ps
docker compose logs --tail 200 <service-name>
```

For TURN deployments, also verify `coturn` is running and the app publishes ICE config:

```bash
docker compose ps coturn
# HTTPS by default; if PIPELINE_TLS=false the HTTPS call fails and the HTTP one returns the config
curl -k https://localhost:${PIPELINE_APP_PORT:-7860}/api/ice-servers \
  || curl http://localhost:${PIPELINE_APP_PORT:-7860}/api/ice-servers
```

App service names follow the active example: `generic-assistant`, `multilingual-assistant`, `omni-assistant`, `omni-assistant-subagents`, or `thinker-talker`. Sidecars keep their own names (`nvidia-llm`, `nvidia-llm-vllm`, `nvidia-llm-vllm-omni`, `nemotron-asr-streaming-english`, `nemotron-asr-streaming-multilingual`, `parakeet-ctc-asr`, `parakeet-rnnt-asr`, `tts-service`, `nemotron-speech`, `booking-server`).

## References

- Hardware details and TURN: `references/platform-deployment.md`
- Generic-only deploy: `references/generic-deploy.md`
- Omni Assistant deploy: `references/omni-assistant-deploy.md`
- Omni Assistant Subagents deploy: `references/omni-assistant-subagents-deploy.md`
- Thinker/Talker deploy: `references/thinker-talker-deploy.md`
