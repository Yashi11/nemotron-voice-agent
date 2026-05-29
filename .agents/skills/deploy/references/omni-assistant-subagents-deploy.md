# Omni Assistant Subagents Cascaded Example — Deployment Reference

Use this reference from the `deploy` skill when deploying the cascaded/omni_assistant_subagents example — Nemotron Omni split across four cooperating Pipecat Subagents (transport, speaker, media analyzer, webcam) that share a single `AgentBus`.

## When to use

Pinning a Docker Compose deployment to the Omni Assistant Subagents example. Recipe profile names encode both the example and the hardware target. Selector modes (`cascaded/all`, `all`) are host-native only — they are not exposed as compose profiles.

This example declares `capabilities: [attachments, webcam]` in `examples_registry.yaml`. The browser UI gates the attachment upload control and the webcam panel on these capabilities, and the backend exposes `POST /api/sessions/{id}/attachments`, `POST /api/sessions/{id}/webcam/frames`, and `GET /api/webcam-config` for them.

Per-example catalogs at `src/cascaded/omni_assistant_subagents/services.{cloud,local}.yaml` are auto-selected on container startup because the registry resolves the example for the active recipe.

Hardware support: cloud-only and `dgxspark`, matching `cascaded/omni-assistant`. The 30B Omni NVFP4 model does not fit on Orin-class hardware today. There is no `jetson` recipe.

## Compose deploy

```bash
# Cloud (NVCF)
docker compose --profile cascaded/omni-assistant-subagents up -d

# DGX Spark (local Omni vLLM + NIM TTS)
docker compose --profile cascaded/omni-assistant-subagents/dgxspark up -d
```

| Recipe profile | App service | Sidecars from `cascaded/shared/` |
| --- | --- | --- |
| `cascaded/omni-assistant-subagents` | `cascaded-omni-assistant-subagents` | none (cloud NVCF) |
| `cascaded/omni-assistant-subagents/dgxspark` | `cascaded-omni-assistant-subagents` | `nvidia-llm-vllm-omni`, `tts-service` |

Tear down with the same recipe used at `up` time.

## Verify

- UI at `https://<host>:7860/` by default, or `http://<host>:7860/` when `PIPELINE_TLS=false`. The sidebar shows a webcam panel and the conversation panel shows an attachment upload control.
- App logs: `docker compose logs --tail 200 cascaded-omni-assistant-subagents`. Look for `Starting Nemotron Omni subagents pipeline ... agents=transport,speaker,media,webcam`.
- Attachment upload check: `curl -F file=@image.jpg "https://<host>:7860/api/sessions/<session_id>/attachments?kind=image"` (use a session id from a live session).
- Webcam config check: `curl -fk https://<host>:7860/api/webcam-config`.

## Common failures

- **`pull access denied` / `unauthorized`** -> NGC login was not done or expired. See the root `deploy` skill.
- **App container exits with `ModuleNotFoundError: pipecat_subagents`** -> dependency desync. Rebuild with `docker compose --profile cascaded/omni-assistant-subagents build`.
- **UI is missing the webcam / attachment surfaces** -> the active example does not declare the `attachments` / `webcam` capability. Verify `EXAMPLE_SELECTION` resolves to `cascaded/omni-assistant-subagents` and `examples_registry.yaml` still lists `capabilities: [attachments, webcam]` on that entry.
- **Webcam panel uploads silently fail** -> browser blocked camera access. Confirm the page is served over HTTPS (`PIPELINE_TLS=true`) or `http://localhost` on the same host.
- **Media analyzer never runs after an upload** -> the speaker LLM did not set `selected_input_source=uploaded_attachment`. Check `cascaded-omni-assistant-subagents` logs for `Speaker Omni queued media analysis trigger`. If absent, the prompt routing rules in `src/cascaded/omni_assistant_subagents/prompts.yaml` were overridden.
- **Omni vLLM issues** -> see `omni-assistant-deploy.md` (same sidecar).
- **Tear-down leaves orphan services after a service rename** -> rerun `up` or `down` with `--remove-orphans`.
