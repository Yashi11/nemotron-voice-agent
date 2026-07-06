# Multilingual - cascaded pipeline example

Multilingual cascaded voice pipeline using Pipecat's built-in NVIDIA services (`NvidiaSTTService` -> `NvidiaLLMService` -> `NvidiaTTSService`). The LLM emits a single JSON object `{"lang_id": "<code>", "response": "<reply>"}` and the pipeline automatically switches the active TTS voice on each detected language change. It can listen, reason, and respond across supported languages while staying deterministic about which text reaches TTS and the UI.

The pattern uses dedicated ASR, LLM, and TTS services with a JSON response contract that drives runtime language and voice switching. It showcases server-side guided JSON decoding plus a per-turn format reminder, the `MultilingualTextAggregator` that streams the spoken `response` and drives early TTS voice updates from `lang_id`, and a clean chat history that stores only the spoken `response`.

![Architecture Diagram](../../../docs/images/arch.png)

## Running the example

This example runs on the **Cloud** (no local GPU, NVCF endpoints), **Workstation** (single GPU), and **DGX Spark** (Blackwell, 128 GB unified memory) profiles and can be extended to **Jetson Thor**, refer the [Jetson Thor guide](../../../docs/03-jetson-thor.md). See the [Getting Started guide](../../../docs/01-getting-started.md) for prerequisites and hardware detail. Run every command from the repository root.

1. Create your `.env` from the template and set your NVIDIA API key:

   ```bash
   cp .env.example .env
   export NVIDIA_API_KEY=<your-nvidia-api-key>
   ```

   > **DGX Spark:** also set `HF_TOKEN` in `.env`. The DGX Spark recipe serves the LLM with vLLM, which downloads the model weights from Hugging Face.

2. Log in to the NVIDIA NGC container registry:

   ```bash
   printf '%s' "$NVIDIA_API_KEY" | docker login nvcr.io -u '$oauthtoken' --password-stdin
   ```

3. Deploy the profile that matches your hardware. The on-prem recipes start a Parakeet RNNT ASR sidecar:

   ```bash
   docker compose --profile multilingual-assistant up -d              # Cloud (no local GPU)
   docker compose --profile multilingual-assistant/workstation up -d  # Workstation
   docker compose --profile multilingual-assistant/dgx-spark up -d    # DGX Spark
   ```

   | Recipe profile | App service | Sidecars |
   | --- | --- | --- |
   | `multilingual-assistant` | `multilingual-assistant` | none (cloud NVCF) |
   | `multilingual-assistant/workstation` | `multilingual-assistant` | `nvidia-llm`, `parakeet-rnnt-asr`, `tts-service` |
   | `multilingual-assistant/dgx-spark` | `multilingual-assistant` | `nvidia-llm-vllm`, `parakeet-rnnt-asr`, `tts-service` |

4. Open the UI at `https://localhost:7860/`. Keep TLS enabled for browser UI testing. `PIPELINE_TLS=false` serves plain HTTP for headless performance and API testing. For plain-HTTP browser testing, see [browser access](../../../docs/06-troubleshooting.md#browser-access).

5. Clean up when you are done by tearing down with the same profile you started with:

   ```bash
   docker compose --profile multilingual-assistant/workstation down
   ```

To run host-native without Docker, set `selection: multilingual-assistant` in [`examples_registry.yaml`](../../../examples_registry.yaml), then run `uv run python3 src/server.py`.

After deploying, validate language switching with the steps in [Testing](#testing).

## Customization

Cloud and on-prem defaults use **Parakeet 1.1B RNNT Multilingual** (`parakeet-rnnt`) via `examples_registry.yaml` and `services.local.yaml`. The `multilingual-assistant/workstation` and `/dgx-spark` recipe profiles start `parakeet-rnnt-asr` locally.

TTS voices and supported language codes are discovered at runtime by prewarming the configured TTS service. The `{lang_codes}` placeholder in the multilingual prompt is replaced automatically with the discovered codes, so no manual language list is needed. The same discovered codes populate the `lang_id` enum used for server-side guided JSON decoding.

Guided JSON decoding is enabled by default and passed to the LLM via `nvext.guided_json` (an OpenAI `extra_body` field). Set `MULTILINGUAL_GUIDED_JSON=0` to disable it if your endpoint does not support guided decoding; the prompt and per-turn reminder still steer the model toward the JSON contract.

| Path | Role |
| --- | --- |
| `pipeline.py` | pipecat entry point, multilingual mode always on |
| `prompts.yaml` | multilingual prompt catalog (`multilingual_voice_assistant`) |
| `services.cloud.yaml` | cloud service endpoints and defaults |
| `services.local.yaml` | on-prem service endpoints (workstation / dgx-spark), registry default `parakeet-rnnt` |

### How it works

1. The LLM returns each response as a single JSON object (`lang_id` first, then `response`):

   ```json
   {"lang_id": "<LangCode>", "response": "<DirectResponse>"}
   ```

2. `MultilingualTextAggregator` parses the streaming JSON and fires a language-switch callback the moment the `lang_id` value closes — before any spoken text streams.
3. The pipeline queues a `TTSUpdateSettingsFrame` to switch the TTS voice before the first sentence of the response is spoken.
4. Only the `response` text is forwarded to TTS, shown in the client transcript, and stored in chat history. `lang_id` never reaches audio, the UI transcript, or the conversation context.
5. `PerTurnReminderProcessor` re-states the JSON/language contract on each user turn at request time only, so the reminder never pollutes stored history.

### Switching the multilingual ASR model

The **Nemotron ASR Streaming Multilingual** sidecar offers lower streaming latency and is best for a fixed single language (see [Model Selection Notes](#model-selection-notes)). To run it instead of the default Parakeet RNNT:

1. In [`examples_registry.yaml`](../../../examples_registry.yaml), under `multilingual-assistant`, set `defaults.asr: [nemotron-asr-streaming-multilingual]`.
2. Redeploy with the recipe profile plus the Nemotron streaming profile, scaling Parakeet off (only one local ASR may bind port `50152`):

   ```bash
   # Workstation
   docker compose --profile multilingual-assistant/workstation \
     --profile nemotron-asr-streaming-multilingual/workstation up -d --scale parakeet-rnnt-asr=0

   # DGX Spark
   docker compose --profile multilingual-assistant/dgx-spark \
     --profile nemotron-asr-streaming-multilingual/dgx-spark up -d --scale parakeet-rnnt-asr=0
   ```

3. Switch back to Parakeet by reversing the registry edit and redeploying the stock on-prem recipe.

## Tips & best practices

### Model Selection Notes

Multilingual behavior depends on the ASR model, the LLM, and the selected TTS voice. Use the notes below when choosing a deployment profile or setting expectations for demo and validation runs.

| Component | Recommendation and trade-offs |
| --- | --- |
| Nemotron ASR Streaming Multilingual | Prefer this model when latency and throughput are the main constraints. It is faster in this pipeline, but recognition quality is currently weaker for a few languages, and language auto-detection is less reliable. For best results, preselect the session language instead of relying on auto-detection. |
| Parakeet 1.1B RNNT Multilingual | Prefer this model when multilingual recognition quality matters more than raw latency. Language auto-detection is relatively stronger, and Hindi and Chinese recognition are generally better than Nemotron ASR in this setup. The trade-off is slower latency and throughput. It can also miss the first word of an utterance in some cases and may produce occasional false transcripts when the microphone is muted or no user speech is intended, so validate turn-start and silence handling for production. |
| Nemotron 3 Super LLM | Recommended over Nemotron 3 Nano when response-format reliability is important. The multilingual pipeline depends on the LLM emitting the `{"lang_id": ..., "response": ...}` JSON contract; guided decoding enforces the structure, and the larger model is generally more reliable at picking the right `lang_id` and staying concise. |
| Nemotron 3 Nano LLM | Useful for lower latency, lower resource usage, and faster local experiments. With reasoning disabled it can drift on free-form formats, which is why guided JSON decoding and the per-turn reminder are enabled by default. For single language, add prompt instructions in target language only  |

### Testing

1. Start the app with the `multilingual-assistant` profile.
2. Speak in English and verify the bot responds in English.
3. Speak in another supported language (for example German, French, or Spanish).
4. Verify that:
   - the spoken response switches to the new language
   - the transcript shows only the clean spoken text (no `lang_id` / JSON braces)
   - the UI language indicator reflects the switched language

### Troubleshooting

| Issue | Cause | What to check |
|-------|-------|---------------|
| Response stays in English | LLM did not emit the expected JSON, or picked the wrong `lang_id` | Verify the prompt/reminder instruct JSON output and, if supported, keep `MULTILINGUAL_GUIDED_JSON` enabled |
| TTS uses the wrong voice or language | Detected language is not supported by the active TTS service | Check the configured TTS service exposes that language code |
| Transcript shows raw JSON (braces / `lang_id`) | LLM emitted text outside the JSON object, or JSON parsing fell back | Confirm you are using the `multilingual-assistant` pipeline; check the endpoint honors guided decoding |
| No voices discovered at startup | TTS prewarm failed | Check TTS sidecar health (`docker compose ps`) and `NVIDIA_API_KEY` |
| Port conflict on the ASR sidecar | Parakeet and Nemotron streaming both bind `50152` | Scale `parakeet-rnnt-asr=0` when running a Nemotron streaming profile |
| Random ASR text while silent | Parakeet RNNT noise sensitivity | Expected with Parakeet. Try the Nemotron Streaming Multilingual opt-in, or reduce room noise using a good mic |

For ASR, LLM, and TTS model details and general failure modes, see [Configure ASR](../../../docs/how-to/configure-asr.md), [Configure TTS](../../../docs/how-to/configure-tts.md), [Configure LLM](../../../docs/how-to/configure-llm.md), and the [Troubleshooting guide](../../../docs/06-troubleshooting.md).
