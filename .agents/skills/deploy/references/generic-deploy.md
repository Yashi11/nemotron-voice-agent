# Generic Cascaded Example — Deployment Reference

Use this reference from the `deploy` skill when deploying only the cascaded/generic voice pipeline example (NVIDIA STT, NIM LLM, NVIDIA TTS with function calling).

## When to use

Deploying only the generic example, not the multi-example selector — use `--profile all-examples` from the root compose otherwise.

Per-example catalogs at `src/cascaded/generic/services.{cloud,local}.yaml` are auto-selected on container startup and when the Generic example is the active UI example.

## Compose deploy

```bash
docker compose --profile <generic|generic-workstation|generic-dgxspark|generic-jetson> up -d
```

| Profile | Example service | Sidecars from `cascaded/shared/` |
| --- | --- | --- |
| `generic` | `generic-example` | none (cloud NVCF) |
| `generic-workstation` | `generic-example` | `nvidia-llm`, `asr-service`, `tts-service` |
| `generic-dgxspark` | `generic-example` | `nvidia-llm-vllm`, `asr-service`, `tts-service` |
| `generic-jetson` | `generic-example` | `nvidia-llm-vllm`, `nemotron-speech` |

Tear down with the same profile:

```bash
docker compose --profile <same-profile> down
```

## Verify

- UI at `https://<host>:7860/` by default, or `http://<host>:7860/` when `PIPELINE_TLS=false`. Locked to **Cascaded → Generic**.
- `docker compose ps` and `docker compose logs --tail 200 generic-example`.

## Common failures

- **`pull access denied` / `unauthorized`** -> NGC login was not done or expired. See the root `deploy` skill.
- **Jetson startup hangs or fails with kernel/CASK errors** -> `riva_init.sh` was not run, or MPS/cpuset is misconfigured. Follow `platform-deployment.md`.
- **Tear-down leaves orphan services after a service rename** -> rerun `up` or `down` with `--remove-orphans`.
