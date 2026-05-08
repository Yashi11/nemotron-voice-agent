# Enable Multilingual Voice Agent

This guide explains how to enable multilingual support in the cascaded pipeline. When a multilingual prompt is selected, the agent can respond in the detected language and automatically switch the active TTS language and voice.

## How Multilingual Support Works

The multilingual flow is prompt-driven. There is no separate environment flag to enable it.

1. Select a multilingual prompt from the UI or set a multilingual prompt key that exists in the active example's `prompts.yaml`.
2. The LLM returns structured output in this format:

```text
Language: <LangCode> Text: <DirectResponse> MetaData: <AdditionalInfo>
```

3. The cascaded multilingual processor:
   - extracts only the `Text` block for speech and UI transcripts
   - switches the active TTS language and voice from the detected `Language`
   - drops the `MetaData` block so it is not spoken

## Requirements

- Use a multilingual-capable ASR service such as Parakeet RNNT Multilingual
- Use a multilingual-capable TTS service such as Magpie Multilingual
- Use a prompt that instructs the model to emit `Language: / Text: / MetaData:` output
- Use an LLM that follows that structured format reliably

## Configuration

Multilingual mode is enabled automatically when the selected prompt key contains `multilingual`.

TTS voices and supported language codes are discovered at runtime from the configured TTS service, so no additional multilingual TTS configuration is required beyond choosing a multilingual-capable service.

## Testing

1. Start the app with a multilingual prompt selected.
2. Speak in one language, for example English.
3. Speak again in another supported language, for example German or French.
4. Verify that:
   - the spoken response switches to the new language
   - the disabled language dropdown reflects the switched language
   - the transcript shows only the spoken `Text` content

## Troubleshooting

| Issue | Cause | What to check |
|-------|-------|---------------|
| Response stays in English | LLM did not emit the expected structured format | Verify the selected prompt is multilingual and the LLM follows `Language: / Text: / MetaData:` |
| TTS uses the wrong voice or language | Detected language is not supported by the active TTS service | Check the configured TTS service exposes that language |
| Transcript shows raw structured output | Multilingual processor is not active for the session | Verify the selected prompt key contains `multilingual` |
