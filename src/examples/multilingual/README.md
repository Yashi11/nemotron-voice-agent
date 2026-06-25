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

Cloud and on-prem defaults use **Parakeet 1.1B RNNT Multilingual** (`parakeet-rnnt`) via
`examples_registry.yaml` and `services.local.yaml`. The `multilingual-assistant/workstation`
and `/dgx-spark` recipe profiles start `parakeet-rnnt-asr` locally.

For Nemotron ASR Streaming Multilingual, use the `nemotron-asr-streaming-multilingual/workstation` or
`nemotron-asr-streaming-multilingual/dgx-spark` Compose profile — see
[Enable Multilingual Voice Agent](../../../docs/how-to/enable-multilingual.md#choosing-a-multilingual-asr-model).

## Model Selection Notes

Multilingual behavior depends on the ASR model, the LLM, and the selected TTS voice.
Use the notes below when choosing a deployment profile or setting expectations for
demo and validation runs.

| Component | Recommendation and trade-offs |
| --- | --- |
| Nemotron ASR Streaming Multilingual | Prefer this model when latency and throughput are the main constraints. It is faster in this pipeline, but Chinese and Hindi recognition quality is currently weaker, and language auto-detection is less reliable. For best results, preselect the session language instead of relying on auto-detection. |
| Parakeet 1.1B RNNT Multilingual | Prefer this model when multilingual recognition quality matters more than raw latency. Language auto-detection is relatively stronger, and Hindi and Chinese recognition are generally better than Nemotron ASR in this setup. The trade-off is slower latency and throughput. It can also miss the first word of an utterance in some cases and may produce occasional false transcripts when the microphone is muted or no user speech is intended, so validate turn-start and silence handling for production-like demos. |
| Nemotron 3 Super LLM | Recommended over Nemotron 3 Nano when response-format reliability is important. The multilingual pipeline depends on the LLM following the `Language: / Text: / MetaData:` contract, and the larger model is generally more reliable at staying within that format. |
| Nemotron 3 Nano LLM | Useful for lower latency, lower resource usage, and faster local experiments, but it may be less consistent about strict structured output under ambiguous or noisy ASR transcripts. |

## Layout

| Path | Role |
| --- | --- |
| `pipeline.py` | pipecat entry point — multilingual mode always on |
| `prompts.yaml` | multilingual prompt catalog |
| `services.cloud.yaml`, `services.local.yaml` | service catalogs; registry default `parakeet-rnnt` |

## How it works

1. The LLM returns each response in this format:
   ```text
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

On-prem recipes (Parakeet RNNT ASR sidecar):

```bash
# Workstation
docker compose --profile multilingual-assistant/workstation up -d

# DGX Spark
docker compose --profile multilingual-assistant/dgx-spark up -d
```

Tear down with the same profile used at `up` time:

```bash
docker compose --profile multilingual-assistant/workstation down
```

| Recipe profile | App service | Sidecars |
| --- | --- | --- |
| `multilingual-assistant` | `multilingual-assistant` | none (cloud NVCF) |
| `multilingual-assistant/workstation` | `multilingual-assistant` | `nvidia-llm`, `parakeet-rnnt-asr`, `tts-service` |
| `multilingual-assistant/dgx-spark` | `multilingual-assistant` | `nvidia-llm-vllm`, `parakeet-rnnt-asr`, `tts-service` |

The UI is served at `https://localhost:7860/` by default. Keep TLS enabled for
browser UI testing; `PIPELINE_TLS=false` is intended for headless performance
and API testing. If you still need HTTP for temporary browser testing, open the
browser flags page (for example,
`chrome://flags/#unsafely-treat-insecure-origin-as-secure` in Chrome or
`edge://flags/#unsafely-treat-insecure-origin-as-secure` in Edge), enable the
`Insecure origins treated as secure` flag, add `http://localhost:7860`,
relaunch the browser, and remove the origin after testing.
