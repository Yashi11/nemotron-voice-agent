# Enable Multilingual Voice Agent

This guide explains how to use the dedicated multilingual cascaded pipeline. The agent
detects the speaker's language per turn and automatically switches the TTS voice and
language to match.

## How Multilingual Support Works

1. The LLM returns each response in this structured format:

   ```text
   Language: <LangCode> Text: <DirectResponse> MetaData: <AdditionalInfo>
   ```

2. The multilingual pipeline:
   - switches the active TTS language and voice the moment `Language: <code>` is parsed
   - forwards only the `Text:` block to TTS and to the client transcript
   - drops `Language:` and `MetaData:` segments — they are never spoken or shown

## Deploying the Multilingual Example

Use the `multilingual-assistant` example:

```bash
# Cloud-only (Parakeet RNNT ASR + Magpie TTS via NVCF)
docker compose --profile multilingual-assistant up -d

# Workstation — local Parakeet RNNT + Magpie TTS + NIM LLM
docker compose --profile multilingual-assistant/workstation up -d

# DGX Spark — local Parakeet RNNT + Magpie TTS + vLLM LLM
docker compose --profile multilingual-assistant/dgx-spark up -d
```

The same `multilingual-assistant/workstation` and `multilingual-assistant/dgx-spark`
recipe profiles now start **`parakeet-rnnt-asr`** (Parakeet 1.1B RNNT Multilingual).
`examples_registry.yaml` defaults to `parakeet-rnnt` at `parakeet-rnnt-asr:50052`.

For host-native runs, set `selection: multilingual-assistant` in
`examples_registry.yaml` and start the server normally.

## Choosing a multilingual ASR model

On-prem and cloud defaults use **Parakeet 1.1B RNNT Multilingual** (`parakeet-rnnt`).
Nemotron ASR Streaming Multilingual is available as an opt-in local sidecar when you need
lower streaming latency or want to compare behavior in a fixed-language deployment.

### Parakeet RNNT Multilingual (default — preferred)

| Pros | Cons |
| --- | --- |
| Best fit for **mixed-language** and **language-switching** sessions | Slightly higher latency than Nemotron streaming ASR |
| Default in `examples_registry.yaml` and the cloud NVCF catalog | May emit **spurious transcripts when the microphone is idle** (noise floor / room tone) |
| Same model family across cloud and local workstation / DGX Spark recipes | |
| Works with the stock on-prem recipe — no extra Compose profiles | |

**When to use:** general multilingual assistants, contact-center or travel use cases, and
any deployment where users may change language mid-conversation. This is the recommended
default for the `multilingual-assistant` example.

### Nemotron ASR Streaming Multilingual (opt-in)

| Pros | Cons |
| --- | --- |
| Lower **streaming** latency; cache-aware NIM | Weaker fit for free **code-switching** across many languages |
| Good for **single-language** agents (e.g. French-only kiosk) | Requires a registry change plus an extra Compose profile |
| | Only one local ASR may bind port `50152` — scale `parakeet-rnnt-asr=0` when Nemotron is running |

**When to use:** experiment when the deployment language is fixed and you want the lowest
local streaming latency. For a single-language kiosk or demo, Nemotron streaming is worth
trying; for the general multilingual example, **Parakeet RNNT remains the preferred default**.

### Switch to Nemotron locally

To run the Nemotron streaming multilingual sidecar instead of Parakeet locally:

1. In `examples_registry.yaml`, under `multilingual-assistant`, set
   `defaults.asr: [nemotron-asr-streaming-multilingual]`.
2. Redeploy with the recipe profile plus the Nemotron streaming profile, and scale
   Parakeet off (only one local ASR may bind port `50152`):

   ```bash
   # Workstation
   docker compose --profile multilingual-assistant/workstation \
     --profile nemotron-asr-streaming-multilingual/workstation up -d --scale parakeet-rnnt-asr=0

   # DGX Spark
   docker compose --profile multilingual-assistant/dgx-spark \
     --profile nemotron-asr-streaming-multilingual/dgx-spark up -d --scale parakeet-rnnt-asr=0
   ```

3. Restart the app container (or the host-native server).

Switch back to Parakeet by reversing the registry edit and redeploying the stock
on-prem recipe.

## Requirements

- **ASR (default)**: Parakeet RNNT Multilingual — `parakeet-rnnt` in
  `examples_registry.yaml`; cloud NVCF or local `parakeet-rnnt-asr:50052`.
- **ASR (opt-in)**: Nemotron ASR Streaming Multilingual — `nemotron-asr-streaming-multilingual/workstation`
  or `nemotron-asr-streaming-multilingual/dgx-spark` Compose profile plus registry change (see above).
- **TTS**: Magpie TTS Multilingual — provides per-language voice switching.
- **LLM**: Any Nemotron model that follows the `Language: / Text: / MetaData:` format
  reliably (Nemotron Super recommended).

## Configuration

TTS voices and supported language codes are discovered at runtime by prewarming the
configured TTS service. The `{lang_codes}` placeholder in the prompt is replaced
automatically with the discovered codes — no manual language list is needed.

To customise the prompt or swap service endpoints, edit the files under
`src/examples/multilingual/`:

| File | Purpose |
| --- | --- |
| `prompts.yaml` | Multilingual prompt (`multilingual_voice_assistant`) |
| `services.cloud.yaml` | Cloud service endpoints and defaults |
| `services.local.yaml` | On-prem service endpoints (workstation / dgxspark) |

## Testing

1. Start the app with the `multilingual-assistant` profile.
2. Speak in English and verify the bot responds in English.
3. Speak in another supported language (e.g. German, French, Spanish).
4. Verify that:
   - the spoken response switches to the new language
   - the transcript shows only the clean spoken text (no `Language:` / `MetaData:` markers)
   - the UI language indicator reflects the switched language

## Troubleshooting

| Issue | Cause | What to check |
|-------|-------|---------------|
| Response stays in English | LLM did not emit the expected structured format | Verify the selected prompt instructs the model to use `Language: / Text: / MetaData:` |
| TTS uses the wrong voice or language | Detected language is not supported by the active TTS service | Check the configured TTS service exposes that language code |
| Transcript shows raw structured output | `skip_aggregator_types` not applied | Confirm you are using the `multilingual-assistant` pipeline, not `generic-assistant` |
| No voices discovered at startup | TTS prewarm failed | Check TTS sidecar health (`docker compose ps`) and `NVIDIA_API_KEY` |
| Port conflict on ASR sidecar | Parakeet and Nemotron both on `50152` | Scale `parakeet-rnnt-asr=0` when using a Nemotron streaming profile |
| Random ASR text while silent | Parakeet RNNT noise sensitivity | Expected with Parakeet; try Nemotron opt-in, tighten mic gain, or reduce room noise |
