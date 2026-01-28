# Multilingual Voice Agent

## Overview

The multilingual voice agent enables seamless conversations across multiple languages by responding in the same language as the user's input, when supported by the TTS model. This feature uses NVIDIA Parakeet RNNT Multilingual ASR, NVIDIA Magpie Multilingual TTS, and NVIDIA Llama Nemotron LLM to create natural conversational experiences. If the user speaks an unsupported language, the system falls back to English.

## What is Multilingual Voice Agent?

A multilingual voice agent can:

- **Respond in Multiple Languages**: Generate spoken responses in the user's language when supported
- **Switch Languages Dynamically**: Handle mid-conversation language changes
- **Fall Back Gracefully**: Default to English when encountering unsupported languages

---

## Key Components

| Component | Description | Documentation |
|-----------|-------------|---------------|
| **NVIDIA Parakeet RNNT ASR** | Transcribes speech in multiple languages | [Parakeet ASR](https://build.nvidia.com/nvidia/parakeet-1_1b-rnnt-multilingual-asr) |
| **NVIDIA Magpie TTS** | Synthesizes speech in multiple languages | [Magpie TTS](https://build.nvidia.com/nvidia/magpie-tts-multilingual) |
| **NVIDIA Llama Nemotron LLM** | Generates multilingual responses with structured language output | [Llama Nemotron](https://build.nvidia.com/nvidia/llama-3_3-nemotron-super-49b-v1_5) |

---

## How It Works

### LLM Response Format

The multilingual system uses a structured output format to coordinate language detection and TTS routing:

```
Language: <LangCode> Text: <DirectResponse> MetaData: <AdditionalInfo>
```

| Field | Description |
|-------|-------------|
| `Language` | Detected language code (e.g., `en-US`, `de-DE`, `fr-FR`) |
| `Text` | The spoken response content—this is what the user hears |
| `MetaData` | Additional context not meant to be spoken (optional) |

**Example Responses:**
```
Language: en-US Text: How can I help you today? MetaData: greeting
Language: de-DE Text: Gerne! Welche Blumen moechten Sie? MetaData: flower inquiry
Language: fr-FR Text: Bonjour! Comment puis-je vous aider? MetaData: none
Language: es-US Text: Hola! Que tipo de flores necesita? MetaData: initial contact
```

### Language Detection Rules

1. **Per-Message Detection**: Language is detected from each user message independently based on LLM analysis of transcripts
2. **Supported Languages Only**: Responses use only languages supported by the TTS model
3. **Graceful Fallback**: Unsupported languages default to `en-US` with English response

---

## Deploying with Multilingual Mode

Follow these steps to deploy the multilingual voice agent:

### Step 1: Copy the Environment Configuration

Copy the template environment file to create your configuration:

```bash
cp config/env.example .env
```

### Step 2: Update .env for Multilingual Mode

Edit the `.env` file and update the following settings:

1. **Enable multilingual mode:**
   ```bash
   ENABLE_MULTILINGUAL=true
   ```

2. **Configure multilingual ASR:**
   ```bash
   RIVA_ASR_IMAGE=nvcr.io/nim/nvidia/parakeet-1-1b-rnnt-multilingual:1.4.0
   RIVA_ASR_MODEL=parakeet-rnnt-1.1b-unified-ml-cs-universal-multi-asr-streaming
   RIVA_ASR_NIM_TAGS=mode=str
   ```

3. **Configure LLM for multilingual (uncomment OPTION 2 block):**
   ```bash
   NVIDIA_LLM_IMAGE=nvcr.io/nim/nvidia/llama-3.3-nemotron-super-49b-v1.5:1.15.4
   NVIDIA_LLM_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1.5
   TEMPERATURE=0
   TOP_P=1.0
   NIM_ENABLE_KV_CACHE_REUSE=1
   SYSTEM_PROMPT_SELECTOR=llama-3.3-nemotron-super-49b-v1.5/multilingual_voice_assistant
   ```

   **Note:** Comment out the default OPTION 1 (Nemotron-3-Nano) configuration.

### Step 3: Deploy with Docker Compose

Start the multilingual voice agent:

```bash
docker compose up -d
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Wrong language response | LLM not following format | Verify `SYSTEM_PROMPT_SELECTOR` is set correctly |
| TTS speaks wrong language | Language code mismatch | Check LLM is outputting valid language codes |
| No speech output | Format parsing failure | Ensure LLM outputs correct `Language: Text: MetaData:` format |
| ASR not transcribing correctly | Using English-only model | Switch to `parakeet-rnnt-1.1b-unified-ml-cs-universal-multi-asr-streaming` |
