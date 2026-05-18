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

## Local LLM NIM profiles

- List profiles before changing LLM precision or tensor parallelism:

```bash
docker run --rm --gpus all \
  -e NGC_API_KEY="$NVIDIA_API_KEY" \
  nvcr.io/nim/nvidia/nemotron-3-nano:1.7.0-variant \
  list-model-profiles
```

- For one GPU, use `tp=1`. Higher `tp` values require that many GPUs.
- Prefer readable tag selection over profile hashes: `NIM_TAGS_SELECTOR=precision=fp8,tp=1`.
- If using NIM defaults, omit `NIM_KV_CACHE_PERCENT` and `NIM_MAX_MODEL_LEN`, but expect high memory use.
- If the local LLM hits OOM, lower `NIM_KV_CACHE_PERCENT` or `NIM_MAX_MODEL_LEN`. On multi-GPU hosts, choose a NIM profile with matching `tp` and expose that many GPUs.
- More details: https://docs.nvidia.com/nim/large-language-models/latest/deployment/model-profiles-and-selection.html

## Common failures

- **`pull access denied` / `unauthorized`** -> NGC login was not done or expired. See the root `deploy` skill.
- **Jetson startup hangs or fails with kernel/CASK errors** -> `riva_init.sh` was not run, or MPS/cpuset is misconfigured. Follow `platform-deployment.md`.
- **Tear-down leaves orphan services after a service rename** -> rerun `up` or `down` with `--remove-orphans`.
