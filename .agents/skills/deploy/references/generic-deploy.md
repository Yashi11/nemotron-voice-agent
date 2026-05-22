# Generic Cascaded Example — Deployment Reference

Use this reference from the `deploy` skill when deploying the cascaded/generic voice pipeline example (NVIDIA STT, NIM LLM, NVIDIA TTS with function calling).

## When to use

Pinning a Docker Compose deployment to the Generic Cascaded example. Compose deployments are per-example only; the `cascaded/generic` profile sets the container's `EXAMPLE_SELECTION` directly. Selector modes (`cascaded/all`, `all`) are host-native only today — they are not exposed as compose profiles.

Per-example catalogs at `src/cascaded/generic/services.{cloud,local}.yaml` are auto-selected on container startup because the registry resolves the example for the active profile.

## Compose deploy

Pick one example profile and optionally combine with a hardware profile:

```bash
docker compose --profile cascaded/generic [--profile <hardware>] up -d
```

| Profile combination | App service | Sidecars from `cascaded/shared/` |
| --- | --- | --- |
| `cascaded/generic` | `cascaded-generic` | none (cloud NVCF) |
| `cascaded/generic` + `workstation` | `cascaded-generic` | `nvidia-llm`, `asr-service`, `tts-service` |
| `cascaded/generic` + `dgxspark` | `cascaded-generic` | `nvidia-llm-vllm`, `asr-service`, `tts-service` |
| `cascaded/generic` + `jetson` | `cascaded-generic` | `nvidia-llm-vllm`, `nemotron-speech` |

Tear down with the same profile combination used at `up` time:

```bash
docker compose --profile cascaded/generic [--profile <hardware>] down
```

## Verify

- UI at `https://<host>:7860/` by default, or `http://<host>:7860/` when `PIPELINE_TLS=false`.
- `docker compose ps` and `docker compose logs --tail 200 cascaded-generic`.

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
