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
- Recipe profile names are `<family>` for cloud-only deployments and `<family>/<hardware>` for on-prem deployments (for example `cascaded-generic` and `cascaded-generic/workstation`). The profile is a complete, self-contained recipe — never combine two recipes.
- Selector modes (`<family>/all`, `all`, e.g. `cascaded-generic/all`) remain host-native only (`uv run`) and have no compose profile.
- Observability profiles (`tracing`, `turn`) compose orthogonally with any recipe.

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

Required keys: `NVIDIA_API_KEY` for all recipes. `HF_TOKEN` for any recipe that ends in `/dgxspark` or `/jetson`.

4. Pick the recipe profile:

| Goal | Recipe profile |
| --- | --- |
| Cloud-only Generic Cascaded | `cascaded-generic` |
| Cloud-only Multilingual Cascaded | `cascaded-multilingual` |
| Cloud-only Omni Assistant | `cascaded-omni` |
| Cloud-only Omni Assistant Subagents | `cascaded-omni` |
| Cloud-only Thinker/Talker Airline Assistant | `cascaded-thinker-talker` |
| Generic Cascaded on a workstation | `cascaded-generic/workstation` |
| Generic Cascaded on DGX Spark | `cascaded-generic/dgx-spark` |
| Generic Cascaded on Jetson Thor | `cascaded-generic/jetson-thor` |
| Multilingual Cascaded on a workstation | `cascaded-multilingual/workstation` |
| Multilingual Cascaded on DGX Spark | `cascaded-multilingual/dgx-spark` |
| Omni Assistant on a workstation | `cascaded-omni/workstation` |
| Omni Assistant on DGX Spark | `cascaded-omni/dgx-spark` |
| Omni Assistant Subagents on DGX Spark | `cascaded-omni/dgx-spark` |
| Thinker/Talker Airline Assistant on a workstation | `cascaded-thinker-talker/workstation` |


For any on-prem recipe, log in to `nvcr.io` first.

5. Start:

```bash
docker compose --profile <recipe> up -d
```

Add observability profiles freely: `--profile tracing` (Phoenix), `--profile turn` (coturn). Use `--build` only after source or `Dockerfile` changes.

6. Verify:

```bash
docker compose ps
docker compose logs --tail 200 <service-name>
```

App service names follow the active recipe family: `cascaded-generic`, `cascaded-multilingual`, `cascaded-omni`, or `cascaded-thinker-talker`. Sidecars keep their own names (`nvidia-llm`, `nvidia-llm-vllm`, `nvidia-llm-vllm-omni`, `asr-service`, `tts-service`, `nemotron-speech`, `booking-server`).

## References

- Hardware details and TURN: `references/platform-deployment.md`
- Generic-only deploy: `references/generic-deploy.md`
- Omni Assistant deploy: `references/omni-assistant-deploy.md`
- Omni Assistant Subagents deploy: `references/omni-assistant-subagents-deploy.md`
- Thinker/Talker deploy: `references/thinker-talker-deploy.md`
