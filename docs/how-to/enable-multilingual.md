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

# Workstation — local Nemotron ASR Streaming Multilingual + Magpie TTS + NIM LLM
docker compose --profile multilingual-assistant/workstation up -d

# DGX Spark — local Nemotron ASR Streaming Multilingual + Magpie TTS + vLLM LLM
docker compose --profile multilingual-assistant/dgx-spark up -d
```

For host-native runs, set `selection: multilingual-assistant` in
`examples_registry.yaml` and start the server normally.

## Requirements

- **ASR**: Cloud uses Parakeet RNNT Multilingual
  (`parakeet-1.1b-rnnt-multilingual-asr`). Local profiles default to
  `nemotron-asr-streaming-multilingual`, backed by the
  `cache-aware-parakeet-rnnt-multi-asr-streaming-sortformer` model with
  `language_code: auto`. Parakeet RNNT remains available as a selectable local
  catalog option.
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
| `services.local.yaml` | On-prem service endpoints (workstation / dgx-spark) |

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
