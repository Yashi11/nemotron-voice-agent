# Multilingual - cascaded pipeline example

Dedicated multilingual cascaded voice pipeline using pipecat's built-in NVIDIA services
(`NvidiaSTTService` -> `NvidiaLLMService` -> `NvidiaTTSService`). The pipeline always
runs in multilingual mode: the LLM emits structured `Language: / Text: / MetaData:`
output and the pipeline automatically switches the active TTS voice on each detected
language change.

Everything specific to this example lives under `src/examples/multilingual/`: pipeline
entry point, service catalogs, and prompts. Shared pipeline helpers live in
`src/examples/shared/pipeline_utils.py`.

## Overview and Use Cases

| Area | Details |
| --- | --- |
| Example intent | A multilingual cascaded assistant that can listen, reason, and respond across supported languages while keeping the pipeline deterministic about which text reaches TTS and the UI. |
| Architecture pattern | Use dedicated ASR, LLM, and TTS services with a structured LLM response contract that drives runtime language and voice switching. |
| What to study | Prompt-enforced `Language: / Text: / MetaData:` output, `MultilingualTextAggregator`, early TTS voice updates, and filtering metadata away from spoken and displayed transcripts. |
| Best fit | Teams building voice experiences for users who switch languages, operate in multilingual regions, or need one deployment to cover multiple customer-language journeys. |
| Extend into | Multilingual contact-center agents, hospitality and travel assistants, global employee support, language-practice companions, translated kiosk flows, or localized field-service copilots. |

Cloud deployments use the existing Parakeet RNNT multilingual ASR endpoint. Local
workstation and DGX Spark deployments default to `nemotron-asr-streaming-multilingual`,
which runs the cache-aware RC1 streaming ASR NIM in multilingual mode with automatic
language detection.

## Layout

| Path | Role |
| --- | --- |
| `pipeline.py` | pipecat entry point — multilingual mode always on |
| `prompts.yaml` | multilingual prompt catalog |
| `services.cloud.yaml`, `services.local.yaml` | service catalogs; local ASR defaults to `nemotron-asr-streaming-multilingual` |

## How it works

1. The LLM returns each response in this format:
   ```
   Language: <LangCode> Text: <DirectResponse> MetaData: <AdditionalInfo>
   ```
2. `MultilingualTextAggregator` parses the structured output and fires a language-switch
   callback the moment the `Language:` code is detected.
3. The pipeline queues a `TTSUpdateSettingsFrame` to switch the TTS voice before the
   first sentence of the response is spoken.
4. Only the `Text:` content is forwarded to TTS and shown in the client transcript.
   `Language:` and `MetaData:` segments are dropped from both audio and the UI.

## Running the example

Host-native (no Docker), set `selection: multilingual-assistant` in
[`examples_registry.yaml`](../../../examples_registry.yaml) at the repo root, then:

```bash
uv run python3 src/server.py
```

Docker — cloud-only:

```bash
docker compose --profile multilingual-assistant up -d
```

On-prem recipes with local ASR / TTS / LLM sidecars:

```bash
# Workstation (`nemotron-asr-streaming-multilingual` + Magpie TTS + NIM LLM)
docker compose --profile multilingual-assistant/workstation up -d

# DGX Spark (`nemotron-asr-streaming-multilingual` + Magpie TTS + vLLM LLM)
docker compose --profile multilingual-assistant/dgx-spark up -d
```

Tear down with the same profile used at `up` time:

```bash
docker compose --profile multilingual-assistant/workstation down
```

| Recipe profile | App service | Sidecars |
| --- | --- | --- |
| `multilingual-assistant` | `multilingual-assistant` | none (cloud NVCF) |
| `multilingual-assistant/workstation` | `multilingual-assistant` | `nvidia-llm`, `nemotron-asr-streaming-multilingual`, `tts-service` |
| `multilingual-assistant/dgx-spark` | `multilingual-assistant` | `nvidia-llm-vllm`, `nemotron-asr-streaming-multilingual`, `tts-service` |

The UI is served at `https://localhost:7860/` by default. Keep TLS enabled for
browser UI testing; `PIPELINE_TLS=false` is intended for headless performance
and API testing. If you still need HTTP for temporary browser testing, open the
browser flags page (for example,
`chrome://flags/#unsafely-treat-insecure-origin-as-secure` in Chrome or
`edge://flags/#unsafely-treat-insecure-origin-as-secure` in Edge), enable the
`Insecure origins treated as secure` flag, add `http://localhost:7860`,
relaunch the browser, and remove the origin after testing.
