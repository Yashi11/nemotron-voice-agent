# Generic Cascaded Example — Deployment Reference

Use this reference from the `deploy` skill when deploying only the cascaded/generic voice pipeline example (NVIDIA STT, NIM LLM, NVIDIA TTS with function calling). The root `deploy` skill covers env, NGC login, and platform selection that this reference assumes is already done.

## When to use

Deploying only the generic example, not the multi-example selector — use `--profile all-examples` from the root compose otherwise.

Per-example catalogs at `src/cascaded/generic/services.{cloud,local}.yaml` are auto-selected for the example container on startup; edit those instead of the root catalogs (see `configure-pipeline`).

## Compose deploy

The root `docker-compose.yml` already includes `cascaded/shared/` and every example compose. Deploy from the repo root using the profile that matches the available hardware:

```bash
docker compose --profile <generic|generic-workstation|generic-dgxspark|generic-jetson> up -d
```

| Profile | Example service | Backends from `cascaded/shared/` |
| --- | --- | --- |
| `generic` | `generic-example` | none (cloud NVCF) |
| `generic-workstation` | `generic-example-workstation` | `nvidia-llm`, `asr-service`, `tts-service` |
| `generic-dgxspark` | `generic-example-dgxspark` | `nvidia-llm-vllm`, `asr-service`, `tts-service` |
| `generic-jetson` | `generic-example-jetson` | `nvidia-llm-vllm`, `nemotron-speech` |

Set `DEPLOYMENT_PLATFORM` in `.env` to match the profile suffix (`workstation`, `dgxspark`, or `jetson`); leave it unset for cloud `generic`.

Tear down with the same profile:

```bash
docker compose --profile <same-profile> down
```

## Verify

- UI at `https://<host>:7860/`. Locked to **Cascaded → Generic**.
- `docker compose ps` and `docker compose logs --tail 200 generic-example[-suffix]` (suffix matches the chosen profile).

## Common failures

- **`pull access denied` / `unauthorized`** -> NGC login was not done or expired. See the root `deploy` skill.
- **Jetson startup hangs or fails with kernel/CASK errors** -> `riva_init.sh` was not run, or MPS/cpuset is misconfigured. Follow the Jetson section in `platform-deployment.md`.
- **Tear-down leaves orphan services after a service rename** -> rerun `up` or `down` with `--remove-orphans`.
