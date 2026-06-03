# Omni Assistant Cascaded Example — Deployment Reference

Use this reference from the `deploy` skill when deploying the cascaded/omni_assistant example — Nemotron 3 Nano Omni handles ASR and LLM in a single multimodal chat-completions call, with Magpie TTS for the spoken reply.

## When to use

Pinning a Docker Compose deployment to the Omni Assistant example. Recipe profile names encode both the example and the hardware target. Selector modes (`cascaded/all`, `all`) are host-native only — they are not exposed as compose profiles.

Per-example catalogs at `src/cascaded/omni_assistant/services.{cloud,local}.yaml` are auto-selected on container startup because the registry resolves the example for the active recipe.

Hardware support: cloud-only, `workstation`, and `dgxspark`. The 30B Omni NVFP4 model does not fit on Orin-class hardware today. There is no `jetson` recipe.

## Compose deploy

```bash
# Cloud (NVCF)
docker compose --profile cascaded-omni up -d

# Workstation / DGX Spark (local Omni vLLM + NIM TTS)
docker compose --profile cascaded-omni/workstation up -d
docker compose --profile cascaded-omni/dgx-spark up -d
```

| Recipe profile | App service | Sidecars from `cascaded/shared/` |
| --- | --- | --- |
| `cascaded-omni` | `cascaded-omni` | none (cloud NVCF) |
| `cascaded-omni/workstation` | `cascaded-omni` | `nvidia-llm-vllm-omni`, `tts-service` |
| `cascaded-omni/dgx-spark` | `cascaded-omni` | `nvidia-llm-vllm-omni`, `tts-service` |

Tear down with the same recipe used at `up` time.

## Verify

- UI at `https://<host>:7860/` by default, or `http://<host>:7860/` when `PIPELINE_TLS=false`.
- App logs: `docker compose logs --tail 200 cascaded-omni`.
- Omni vLLM logs (local recipes only): `docker compose logs --tail 200 nvidia-llm-vllm-omni`.
- Omni vLLM health: `curl -f http://localhost:8002/health` from the host or `curl -f http://nvidia-llm-vllm-omni:8002/health` from inside the compose network.

## Common failures

- **`pull access denied` / `unauthorized`** -> NGC login was not done or expired. See the root `deploy` skill.
- **Omni vLLM stuck on first-run model download** -> initial download of `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4` from Hugging Face requires `HF_TOKEN` in `.env`. Allow up to 30 minutes on first start.
- **Out-of-memory on local Omni recipes** -> lower `--gpu-memory-utilization` or `--max-model-len` in `docker/docker-compose.nemotron3-omni.yaml` under the `nvidia-llm-vllm-omni` command.
- **Tear-down leaves orphan services after a service rename** -> rerun `up` or `down` with `--remove-orphans`.
