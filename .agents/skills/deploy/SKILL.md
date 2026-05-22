---
name: deploy
description: Deploy Nemotron Voice Agent via root compose for cloud-only, workstation, DGX Spark, or Jetson. Use when deploying or troubleshooting auth/startup.
version: "1.0.0"
metadata:
  author: Ashutosh Rautela <arautela@nvidia.com>
  tags: [deployment, docker-compose, voice-agent, nemotron]
---

# Nemotron Voice Agent Deployment

## Rules

- Run commands from the repository root containing `docker-compose.yml`.
- Use Docker Compose for deployment.
- Preserve existing `.env`; create it only if missing.
- Use `configure-pipeline` for `.env`, catalog, or prompt changes.
- Every deployment composes **one example profile** with **at most one hardware profile** (plus optional observability profiles). `docker compose up` with no profile is a no-op.
- Compose deployments are per-example only — each profile pins one example. Selector modes (`cascaded/all`, `all` etc.) are host-native (`uv run`) only and have no compose profile.
- Example profile names match the registry keys verbatim: `cascaded/generic`, `cascaded/agentic-airline`, `speech-to-speech/generic`.
- Hardware profiles (`workstation`, `dgxspark`, `jetson`) are platform-specific and not interchangeable.

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
- `workstation`: non-DGX Spark, non-Jetson host with enough GPU VRAM for the selected local NIM services; single-GPU hosts are valid when capacity is sufficient.
- _(omit)_: local platform requirements are not met, or remote/NVCF services are preferred (cloud-only).

3. Prepare `.env`:

```bash
test -f .env || cp .env.example .env
```

Required keys: `NVIDIA_API_KEY` for all modes; `HF_TOKEN` for `dgxspark` and `jetson`.

4. Compose the profile pair:

| Goal | Example profile | Hardware profile |
| --- | --- | --- |
| Cloud-only Generic Cascaded | `cascaded/generic` | _(none)_ |
| Cloud-only Agentic Airline | `cascaded/agentic-airline` | _(none)_ |
| Cloud-only Speech-to-Speech | `speech-to-speech/generic` | _(none)_ |
| Generic Cascaded on a workstation | `cascaded/generic` | `workstation` |
| Generic Cascaded on DGX Spark | `cascaded/generic` | `dgxspark` |
| Generic Cascaded on Jetson Thor | `cascaded/generic` | `jetson` |
| Agentic Airline on a workstation | `cascaded/agentic-airline` | `workstation` |

Hardware profiles are generic Compose overlays. This matrix is representative, not exhaustive: `workstation`, `dgxspark`, and `jetson` can be combined with example profiles unless an example-specific README documents a limitation. Some unlisted combinations may start sidecars that do not match that example's service slots.

For any hardware profile, log in to `nvcr.io` first.

5. Start:

```bash
docker compose --profile <example> [--profile <hardware>] up -d
```

Add observability profiles freely: `--profile tracing` (Phoenix), `--profile turn` (coturn). Use `--build` only after source or `Dockerfile` changes.

6. Verify:

```bash
docker compose ps
docker compose logs --tail 200 <service-name>
```

Service names follow the profile: `cascaded-generic`, `cascaded-agentic-airline`, or `speech-to-speech-generic`. Sidecars keep their own names (`booking-server`, `nvidia-llm`, `asr-service`, etc.).

## References

- Hardware details and TURN: `references/platform-deployment.md`
- Generic-only deploy: `references/generic-deploy.md`
- Agentic Airline deploy: `references/agentic-airline-deploy.md`
