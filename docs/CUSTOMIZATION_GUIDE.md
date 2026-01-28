# Nemotron Voice Agent Customization Guide

This guide provides detailed instructions for customizing the Nemotron Voice Agent to meet your specific needs. You can switch models, configure voices, adjust system prompts, and optimize deployment for your hardware.

## Table of Contents

1. [Single GPU Device Deployment](#single-gpu-device-deployment)
2. [Switching LLM Models](#switching-llm-models)
3. [Switching System Prompts](#switching-system-prompts)
4. [Configuring TTS Voices](#configuring-tts-voices)
5. [Enabling Zero-shot TTS](#enabling-zero-shot-tts)
6. [Advanced Pipeline Customizations](#advanced-pipeline-customizations)

---

## Single GPU Device Deployment

The default `docker-compose.yml` configuration uses a multi-GPU setup with ASR and TTS on one GPU device and LLM on another GPU device. For deploying on single GPU, we need to consider following things

- **Memory Requirements**: Ensure your GPU has sufficient VRAM for all three models, 80+ GB VRAM recommended
- **Performance**: Single GPU deployment may have slightly higher latency due to resource sharing
- **Model Selection**: Consider using smaller models like `Llama-3.1-8b-Instruct` for single GPU setups
- **LLM KV Cache**: By default NVIDIA LLM NIMs, utilize 90% of GPU VRAM with KV caching enabled. Disable or reduce KV Cache memory usage using `NIM_KVCACHE_PERCENT` and `NIM_ENABLE_KV_CACHE_REUSE` environment variables in `nvidia-llm` service. Check [NIM Documentation](https://docs.nvidia.com/nim/large-language-models/latest/kv-cache-reuse.html).

To deploy all services on a single GPU device, edit `docker-compose.yml` to set all services to use the same GPU:

```yaml
# Change device_ids to ['0'] for all services
riva-tts-magpie:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ['0']  # Single GPU
            capabilities: [gpu]

riva-asr-parakeet:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ['0']  # Single GPU
            capabilities: [gpu]

nvidia-llm:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ['0']  # Single GPU
            capabilities: [gpu]
```

---

## Switching LLM Models

The Nemotron Voice Agent supports multiple LLM models with different capabilities and resource requirements. Configure your desired model by editing the `.env` file.

### Local LLM Deployment
1. **Copy the example configuration**:
   ```bash
   cp config/env.example .env
   ```

2. **Edit `.env` file**:
   - Comment out the current model configuration (add `#` at the beginning of each line)
   - Uncomment your desired model configuration block
   - Ensure `SYSTEM_PROMPT_SELECTOR` matches your model name

3. **Restart the services**:
   ```bash
   docker compose down
   docker compose up
   ```

### Using Cloud Endpoints

Instead of local deployment, you can use NVIDIA's cloud-hosted models:

```bash
# In .env file
NVIDIA_LLM_URL=https://integrate.api.nvidia.com/v1
NVIDIA_LLM_MODEL=nvidia/nemotron-3-nano-30b-a3b  # Cloud model name
NVIDIA_API_KEY=your_api_key_here
```

**Note**: Comment out or remove the `nvidia-llm` service from `docker-compose.yml` when using cloud endpoints.

---

## Switching System Prompts

System prompts define your voice agent's personality, behavior, and response format. The agent supports multiple pre-configured prompts for different use cases.

### Available Prompt Templates

All prompts are defined in `config/prompt.yaml`. The format is: `model-name/prompt-name`

#### Generic Voice Assistant
**Purpose**: General-purpose helpful assistant with concise responses

```bash
# In .env file
SYSTEM_PROMPT_SELECTOR=nemotron-3-nano/generic_voice_assistant
# or
SYSTEM_PROMPT_SELECTOR=llama-3.3-nemotron-super-49b-v1.5/generic_voice_assistant
```

#### Flowershop Assistant (Flora)
**Purpose**: Domain-specific assistant for a flower shop

```bash
# In .env file
SYSTEM_PROMPT_SELECTOR=llama-3.1-8b-instruct/flowershop
```

**Characteristics**:
- Persona: Flora from GreenForce Garden
- Handles order management, consultations, delivery coordination

#### TTS Emotion Tags
**Purpose**: Dynamic emotional TTS with real-time emotion control

```bash
# In .env file
SYSTEM_PROMPT_SELECTOR=llama-3.1-8b-instruct/tts_emotion_tags
```

**Output Format**:
```
Emotion: <Happy|Calm|Neutral|Sad|Angry|Fearful> Text: <response>
```

**Characteristics**:
- LLM outputs emotion tags parsed by the pipeline
- TTS voice changes based on emotion context
- Supported emotions: Happy, Calm, Neutral, Sad, Angry, Fearful
- **Requirements**: Only works with Magpie Multilingual TTS model
- **Configuration**: Set `CHAT_HISTORY_LIMIT=3` for best results

#### Multilingual Voice Assistant
**Purpose**: Multi-language support with automatic language detection

```bash
# In .env file
SYSTEM_PROMPT_SELECTOR=llama-3.3-nemotron-super-49b-v1.5/multilingual_voice_assistant
ENABLE_MULTILINGUAL=true
```

**Output Format**:
```
Language: <LangCode> Text: <response> MetaData: <context>
```

**Supported Languages**: en-US, de-DE, fr-FR, es-US, es-ES (configurable in prompt.yaml)

### Creating Custom Prompts

1. **Edit `config/prompt.yaml`**:

```yaml
your-model-name:
  custom_prompt_name:
    description: "Your prompt description"
    messages:
      - role: system
        content: |
          Your system prompt here...
          Define personality, rules, and response format.
```

2. **Update `.env`**:

```bash
SYSTEM_PROMPT_SELECTOR=your-model-name/custom_prompt_name
```

3. **Best Practices**:
   - Keep responses concise (1-2 sentences, <200 characters)
   - Avoid special characters like `*`, `-`, `/` in output
   - No bullet points or numbered lists (breaks voice flow)
   - Define clear output format for structured data
   - Use plain text only

---

## Configuring TTS Voices

The Text-to-Speech system supports multiple voices and languages through the Magpie TTS models.

### Default Multilingual Voice

```bash
# In .env file
RIVA_TTS_IMAGE=nvcr.io/nim/nvidia/magpie-tts-multilingual:1.6.0
RIVA_TTS_VOICE_ID=Magpie-Multilingual.EN-US.Aria
RIVA_TTS_MODEL=magpie_tts_ensemble-Magpie-Multilingual
RIVA_TTS_LANGUAGE=en-US
RIVA_TTS_NIM_TAGS=name=magpie-tts-multilingual,batch_size=32
```

The voice ID format is: `Model.Language.VoiceName`


**Note**: Voice availability depends on your Magpie TTS model version. Refer to [NVIDIA Magpie TTS documentation](https://docs.nvidia.com/nim/riva/tts/latest/getting-started.html#running-inference) for the complete voice list.

### Using Cloud TTS Endpoints

```bash
# In .env file
RIVA_TTS_URL=grpc.nvcf.nvidia.com:443
NVIDIA_API_KEY=your_api_key_here
```

Comment out the `riva-tts-magpie` service in `docker-compose.yml` when using cloud endpoints.

### Pronunciation Correction (IPA)

Customize word pronunciation using International Phonetic Alphabet (IPA):

1. **Edit `config/ipa.json`**:

```json
{
  "GreenForce": "ɡriːn fɔrs",
  "API": "eɪ piː aɪ",
  "NVIDIA": "ɛn vɪd i ə"
}
```

2. **Configure in `.env`**:

```bash
TTS_IPA_FILE_PATH=./config/ipa.json
```

The pipeline automatically applies IPA corrections to TTS output.

---

## Enabling Zero-shot TTS

Zero-shot TTS allows you to clone any voice using a short audio sample (5+ seconds). This feature uses the Magpie Zero-shot model. Apply for access [here](https://developer.nvidia.com/riva-tts-zeroshot-models).

### Step 1: Prepare Your Audio Sample

**Requirements**:
- **Format**: WAV (16-bit PCM recommended)
- **Duration**: 5+ seconds of clean speech
- **Quality**: Clear, no background noise
- **Language**: Should match your target language
- **Speaker**: Single speaker only

**Example**:
```bash
# Create audio_prompts directory
mkdir -p audio_prompts

# Add your voice sample
# audio_prompts/custom_voice.wav
```

### Step 2: Update .env Configuration

```bash
# In .env file

# Comment out standard TTS configuration
#RIVA_TTS_IMAGE=nvcr.io/nim/nvidia/magpie-tts-multilingual:1.6.0
#RIVA_TTS_VOICE_ID=Magpie-Multilingual.EN-US.Aria
#RIVA_TTS_MODEL=magpie_tts_ensemble-Magpie-Multilingual
#RIVA_TTS_NIM_TAGS=name=magpie-tts-multilingual,batch_size=32

# Enable Zero-shot TTS
RIVA_TTS_IMAGE=<ZEROSHOT_DOCKER_IMAGE> # Use your version
RIVA_TTS_VOICE_ID=Magpie-ZeroShot.Female-1
RIVA_TTS_MODEL=magpie_tts_ensemble-Magpie-ZeroShot
RIVA_TTS_NIM_TAGS=name=magpie-tts-zeroshot,batch_size=32
ZERO_SHOT_AUDIO_PROMPT=audio_prompts/custom_voice.wav
```

### Step 3: Update docker-compose.yml

Update the `python-app` service to mount audio prompts:

```yaml
python-app:
  # ... existing configuration ...
  volumes:
    - ./audio_dumps:/app/audio_dumps
    - ./config/:/app/config/
    - ./audio_prompts:/app/audio_prompts  # Add this line
```

### Step 4: Deploy

```bash
# Start services
docker compose up
```

---

## Switching to WebSocket Transport

By default, the Nemotron Voice Agent uses WebRTC for real-time communication. You can switch to WebSocket transport for different deployment scenarios or client requirements.

Update your `.env` file to enable WebSocket transport:

```bash
# In .env file
TRANSPORT=WEBSOCKET
```

Deploy with WebSocket

```bash
# Restart services to apply transport change
docker compose down
docker compose up
```

The system automatically loads the appropriate pipeline and UI based on the `TRANSPORT` setting. After starting the services, access the web interface through your browser at `http://your-server-ip:9000`.

---

## Advanced Pipeline Customizations

### Speculative Speech Processing

Reduces bot response latency by processing interim ASR transcripts instead of waiting for final transcripts.

**Enable/Disable**:
```bash
# In .env file
ENABLE_SPECULATIVE_SPEECH=true  # Default: true
```

**Requirements**:
- Only works with Riva ASR
- See [Speculative Speech Processing docs](./SPECULATIVE_SPEECH_PROCESSING.md) for details

### Chat History Limit

Controls conversation context window:

```bash
# In .env file
CHAT_HISTORY_LIMIT=20  # Number of conversation turns to retain
```

**Recommendations**:
- **Standard conversations**: 20 (default)
- **Emotion-aware TTS**: 3-5 (better emotion tracking)
- **Multilingual mode**: 3-5 (better language detection)


### Audio Debugging

Enable audio dumps for analysis:

```bash
# In .env file
AUDIO_DUMP_PATH=./audio_dumps
```

Audio files are saved to `./audio_dumps/` directory for debugging ASR and TTS quality issues.

### Audio Output Buffering

Control audio output latency and stability by adjusting the buffer size:

```bash
# In .env file
AUDIO_OUT_10MS_CHUNKS=5  # Number of 10ms chunks to buffer
```

**Configuration Guidelines**:
- **Default WebRTC**: 5 chunks (50ms buffer) - optimized for low latency
- **Default WebSocket**: 10 chunks (100ms buffer) - more stable for network variations
- **High Concurrency**: 10-40 chunks (100-400ms buffer) - prevents audio glitches under load


---

For additional information, see:
- [Multilingual Configuration](./MULTILINGUAL.md)
- [Speculative Speech Processing](./SPECULATIVE_SPEECH_PROCESSING.md)
- [Best Practices](./BEST_PRACTICES.md)
- [NVIDIA Pipecat Documentation](./NVIDIA_PIPECAT.md)
