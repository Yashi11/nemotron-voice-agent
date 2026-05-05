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
- Local profiles are platform-specific: `*-workstation`, `*-dgxspark`, and `*-jetson` are not interchangeable. Keep the profile suffix, `DEPLOYMENT_PLATFORM`, and detected hardware aligned.
- Cloud-only profiles (`all-examples`, `generic`, `agentic-airline`) use remote/NVCF services and can run on any platform with Docker.
- For multilingual setup, deploy the target profile first, then use `configure-pipeline` to set the prompt and ASR/TTS defaults.

## Deploy

1. Check hardware:

```bash
cat /sys/class/dmi/id/product_name 2>/dev/null || true
cat /proc/device-tree/model 2>/dev/null || true
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader
free -h
```

2. Identify the deployment target:
- `jetson`: `/proc/device-tree/model` identifies a Jetson platform, or the GPU name is `NVIDIA Thor`.
- `dgxspark`: `/sys/class/dmi/id/product_name` contains `DGX Spark` or `DGX_Spark` case-insensitively.
- `workstation`: non-DGX Spark, non-Jetson host with GPUs `0` and `1` available for local NIM services.
- `cloud-only`: local platform requirements are not met, or remote/NVCF services are preferred.

3. Prepare `.env`:

```bash
test -f .env || cp .env.example .env
```

Required keys: `NVIDIA_API_KEY` for all modes; `HF_TOKEN` for `dgxspark` and `jetson`.

4. Select profile:
- Selector app: `all-examples` (cloud/NVCF only)
- Generic: `generic`, `generic-workstation`, `generic-dgxspark`, `generic-jetson`
- Agentic Airline: `agentic-airline`, `agentic-airline-workstation` (no DGX Spark / Jetson local profile)
- For local profiles, set `DEPLOYMENT_PLATFORM=workstation|dgxspark|jetson` in `.env`.
- For local profiles, log in to `nvcr.io`.

5. Start:

```bash
docker compose --profile <profile> up -d
```

Use `--build` only after source or `Dockerfile` changes.

6. Verify:

```bash
docker compose ps
# Service name depends on profile: all-examples, generic-example[-suffix],
# or agentic-airline-example[-workstation].
docker compose logs --tail 200 <example-service>
```

## References

- Hardware details and TURN: `references/platform-deployment.md`
- Generic-only deploy: `references/generic-deploy.md`
- Agentic Airline deploy: `references/agentic-airline-deploy.md`
