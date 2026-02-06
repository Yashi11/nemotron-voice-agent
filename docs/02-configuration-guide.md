# Nemotron Voice Agent Configuration Guide

This guide provides detailed instructions on configuring the Nemotron Voice Agent to meet your specific needs. You can switch models, configure voices, adjust system prompts, and optimize deployment for your hardware.

## Table of Contents

1. [Switching LLM Models](#switching-llm-models)
2. [Switching System Prompts](#switching-system-prompts)
3. [Configuring TTS Settings](#configuring-tts-settings)
4. [Enabling Zero-shot TTS](#enabling-zero-shot-tts)
5. [Choosing a Transport Method](#choosing-a-transport-method)
6. [Enabling OpenTelemetry Tracing](#enabling-opentelemetry-tracing)
7. [Advanced Pipeline Customizations](#advanced-pipeline-customizations)

---

## Switching LLM Models

The Nemotron Voice Agent supports multiple LLM models with different capabilities and resource requirements. Configure your desired model by editing the [.env](../config/env.example) file.

### Using Local LLM NIM Microservice

1. Copy the example configuration [.env](../config/env.example):

    ```bash
    cp config/env.example .env
    ```

2. Edit the `.env` file. The file contains four pre-configured model blocks. To switch models, comment out the current block and uncomment your desired model.

    **Example: Switch from Nemotron-3-Nano (default) to Llama-3.3-Nemotron-Super-49B**

    Comment out the default configuration:

    ```bash
    # ----------------------------------------------------------------------------
    # OPTION 1: Nemotron-3-Nano (comment out this block)
    # ----------------------------------------------------------------------------
    # NVIDIA_LLM_IMAGE=nvcr.io/nim/nvidia/nemotron-3-nano:1.5.1-variant
    # NVIDIA_LLM_MODEL=nvidia/nemotron-3-nano
    # TEMPERATURE=1.0
    # TOP_P=1.0
    # ENABLE_THINKING=false
    # MAX_TOKENS=2048
    # NIM_ENABLE_BUDGET_CONTROL=1
    # NIM_ENABLE_KV_CACHE_REUSE=1
    # SYSTEM_PROMPT_SELECTOR=nemotron-3-nano/generic_voice_assistant
    ```

    Uncomment the desired model:

    ```bash
    # ----------------------------------------------------------------------------
    # OPTION 2: Llama-3.3-Nemotron-Super-49B (uncomment this block)
    # ----------------------------------------------------------------------------
    NVIDIA_LLM_IMAGE=nvcr.io/nim/nvidia/llama-3.3-nemotron-super-49b-v1.5:1.15.4
    NVIDIA_LLM_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1.5
    TEMPERATURE=0
    TOP_P=1.0
    NIM_ENABLE_KV_CACHE_REUSE=1
    SYSTEM_PROMPT_SELECTOR=llama-3.3-nemotron-super-49b-v1.5/generic_voice_assistant
    ```

    > **Note:** Each model has a matching `SYSTEM_PROMPT_SELECTOR` value. Use the prompt selector that corresponds to your chosen model. For more information about the system prompts, see [Applying System Prompts](#applying-system-prompts).

3. Restart the services:

    ```bash
    docker compose down
    docker compose up
    ```

### Using Cloud Endpoints

Instead of local deployment, you can use NVIDIA's cloud-hosted models on build.nvidia.com. For example, you can set up the `.env` file to use the Nemotron-3-Nano model on build.nvidia.com as follows.

```bash
# In .env file
NVIDIA_LLM_URL=https://integrate.api.nvidia.com/v1
NVIDIA_LLM_MODEL=nvidia/nemotron-3-nano-30b-a3b  # Cloud model name
NVIDIA_API_KEY=your_api_key_here
```

**Note**: Comment out or remove the `nvidia-llm` service from [docker-compose.yml](../docker-compose.yml) when using cloud endpoints.

---

## Applying System Prompts

You can customize your voice agent's personality, behavior, and response format using system prompts.

To set up a system prompt, the following environment variable must be set in the `.env` file:
- `PROMPT_FILE_PATH`: The path to the prompt file to use. The prompt file has a collection of system prompts. In this blueprint, the prompt file is [config/prompt.yaml](../config/prompt.yaml).
- `SYSTEM_PROMPT_SELECTOR`: The name of the system prompt to use from the prompt file. The format is: `model-name/prompt-name`

This blueprint includes several pre-configured prompt samples for various use cases.

### Using System Prompt Samples

The following are examples of calling the system prompt samples available in the blueprint's config file [config/prompt.yaml](../config/prompt.yaml).

#### Generic Voice Assistant

To use the generic voice assistant prompt sample, set the `SYSTEM_PROMPT_SELECTOR` in the `.env` file as follows.

```bash
# In .env file
SYSTEM_PROMPT_SELECTOR=nemotron-3-nano/generic_voice_assistant
# or
SYSTEM_PROMPT_SELECTOR=llama-3.3-nemotron-super-49b-v1.5/generic_voice_assistant
```

#### Flowershop Assistant

To use the flowershop assistant prompt sample, set the `SYSTEM_PROMPT_SELECTOR` in the `.env` file as follows.

```bash
# In .env file
SYSTEM_PROMPT_SELECTOR=llama-3.1-8b-instruct/flowershop
```

**Characteristics**:
- Persona: Flora from GreenForce Garden
- Handles order management, consultations, delivery coordination

#### TTS Emotion Tags

To use the TTS emotion tags prompt sample, set the `SYSTEM_PROMPT_SELECTOR` in the `.env` file as follows. This prompt sample is for a dynamic emotional TTS with real-time emotion control.

```bash
# In .env file
SYSTEM_PROMPT_SELECTOR=llama-3.1-8b-instruct/tts_emotion_tags
```

The generated LLM output format with this system prompt is as follows.
```
Emotion: <Happy|Calm|Neutral|Sad|Angry|Fearful> Text: <response>
```

The following are the characteristics of this prompt.
- LLM outputs emotion tags parsed by the pipeline.
- TTS voice changes based on emotion context.
- Supported emotions: `Happy`, `Calm`, `Neutral`, `Sad`, `Angry`, `Fearful`.
- **Requirements**: Supported only with the Magpie Multilingual TTS model in English (en-US).
- **Configuration**: Set `CHAT_HISTORY_LIMIT=3` for best results.

#### Multilingual Voice Assistant

To use the multilingual voice assistant prompt sample, set the `SYSTEM_PROMPT_SELECTOR` in the `.env` file as follows. This prompt sample is for a multi-language support with automatic language detection.

```bash
# In .env file
SYSTEM_PROMPT_SELECTOR=llama-3.3-nemotron-super-49b-v1.5/multilingual_voice_assistant
ENABLE_MULTILINGUAL=true
```

The generated LLM output format with this system prompt is as follows.

```
Language: <LangCode> Text: <response> MetaData: <context>
```

The supported languages are en-US, de-DE, fr-FR, es-US, es-ES. You can also add other languages to the list in the `lang_codes` variable in [config/prompt.yaml](../config/prompt.yaml).

### Creating Custom Prompts

1. Add you own system prompt to the prompt file [config/prompt.yaml](../config/prompt.yaml) by following the format below.

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

    When creating your own system prompt for outputting text, follow these best practices:
    - Keep responses concise (1-2 sentences, less than 200 characters).
    - Avoid special characters like `*`, `-`, `/` in output.
    - Avoid bullet points or numbered lists (breaks voice flow).
    - Define clear output format for structured data.
    - Use plain text only.

2. Update the `SYSTEM_PROMPT_SELECTOR` in the `.env` file to use your custom prompt.

    ```bash
    SYSTEM_PROMPT_SELECTOR=your-model-name/custom_prompt_name
    ```

---

## Configuring TTS Settings

The Text-to-Speech (TTS) system supports multiple voices and languages through the [NVIDIA Magpie TTS model](https://build.nvidia.com/nvidia/magpie-tts-multilingual/modelcard).

### Default Multilingual TTS Voice

```bash
# In .env file
RIVA_TTS_IMAGE=nvcr.io/nim/nvidia/magpie-tts-multilingual:1.6.0
RIVA_TTS_VOICE_ID=Magpie-Multilingual.EN-US.Aria
RIVA_TTS_MODEL=magpie_tts_ensemble-Magpie-Multilingual
RIVA_TTS_LANGUAGE=en-US
RIVA_TTS_NIM_TAGS=name=magpie-tts-multilingual,batch_size=32
```

The voice ID format of the Magpie Multilingual TTS model is `Model.Language.VoiceName`.

**Note**: The available voices depend on your Magpie TTS model version. Refer to the [NVIDIA Magpie TTS documentation](https://docs.nvidia.com/nim/riva/tts/latest/support-matrix.html#available-voices) for the complete voice list.

### Using Cloud TTS Endpoints

1. Set up the following environment variables in the `.env` file to use the Magpie Multilingual TTS model on NVIDIA's cloud endpoint.

    ```bash
    # In .env file
    RIVA_TTS_URL=grpc.nvcf.nvidia.com:443
    NVIDIA_API_KEY=your_api_key_here
    ```

2. Comment out the `riva-tts-magpie` service in [docker-compose.yml](../docker-compose.yml) when using cloud endpoints.

### Pronunciation Correction

You can customize word pronunciation using International Phonetic Alphabet (IPA).

1. Edit [config/ipa.json](../config/ipa.json) and add custom word-to-IPA mappings:

    ```json
    {
      "NVIDIA": "ˈɛnˌvɪdiə",
      "GreenForce": "ɡriːn fɔrs",
      "API": "eɪ piː aɪ"
    }
    ```

2. Set the environment variable `TTS_IPA_FILE_PATH` to the path of the IPA file. In the example [.env](../config/env.example) file, the IPA file path is set to `./config/ipa.json`.

    ```bash
    TTS_IPA_FILE_PATH=./config/ipa.json
    ```

The pipeline automatically applies IPA corrections to TTS output.

### Adding Text Filters

Apply text filters to remove special characters that can cause Magpie TTS failures.

```bash
# In `.env`
ENABLE_RIVA_TEXT_FILTER=true  # Default: true
```

Consider the following when adding text filters:

- The filter runs only for `RIVA_TTS_LANGUAGE=en-US` and is skipped for other languages.
- To add custom rules, edit `nvidia-pipecat/src/nvidia_pipecat/utils/riva_text_filter.py`.

---

## Enabling Zero-shot TTS

Zero-shot TTS allows you to clone any voice using a short audio sample (5+ seconds). This feature uses the Magpie Zero-shot model. Apply for access [here](https://developer.nvidia.com/riva-tts-zeroshot-models).

1. Prepare your audio sample to meet the following requirements.
   - Audio format is WAV (16-bit PCM recommended).
   - Audio duration is at least 5 seconds of clean speech.
   - Audio quality is clear, no background noise.
   - Language should match your target language.
   - Speaker is single speaker only.

2. Create the `audio_prompts` directory and add your voice sample as `custom_voice.wav`.

    ```bash
    mkdir -p audio_prompts
    cp <your_audio_file>.wav audio_prompts/<your_audio_file>.wav
    ```

3. Run the Magpie zero-shot NIM microservice following the instructions in the [NVIDIA NIM RIVA TTS documentation](https://docs.nvidia.com/nim/riva/tts/latest/getting-started.html#launching-the-nim).

4. Set the environment variables in the `.env` file as follows.

    ```bash
    # Comment out standard TTS configuration
    #RIVA_TTS_IMAGE=nvcr.io/nim/nvidia/magpie-tts-multilingual:1.6.0
    #RIVA_TTS_VOICE_ID=Magpie-Multilingual.EN-US.Aria
    #RIVA_TTS_MODEL=magpie_tts_ensemble-Magpie-Multilingual
    #RIVA_TTS_NIM_TAGS=name=magpie-tts-multilingual,batch_size=32

    # Enable Zero-shot TTS
    RIVA_TTS_IMAGE=<ZEROSHOT_NIM_MICROSERVICE_IMAGE> # Use your version
    RIVA_TTS_VOICE_ID=Magpie-ZeroShot.Female-1
    RIVA_TTS_MODEL=magpie_tts_ensemble-Magpie-ZeroShot
    RIVA_TTS_NIM_TAGS=name=magpie-tts-zeroshot,batch_size=32
    ZERO_SHOT_AUDIO_PROMPT=audio_prompts/custom_voice.wav
    ```

5. Update the `python-app` service in [docker-compose.yml](../docker-compose.yml) to mount audio prompts:

    ```yaml
    python-app:
      # ... existing configuration ...
      volumes:
        - ./audio_dumps:/app/audio_dumps
        - ./config/:/app/config/
        - ./audio_prompts:/app/audio_prompts  # Add this line
    ```

6. Deploy the services:

    ```bash
    docker compose up
    ```

---

## Choosing a Transport Method

By default, the Nemotron Voice Agent blueprint uses web real-time communication (WebRTC). You can switch to WebSocket transport for different deployment scenarios or client requirements.

| Transport | Best For | Latency | Network Requirements |
|-----------|----------|---------|----------------------|
| **WebRTC** (default) | Production voice interactions, lowest latency | ~50-150ms | Requires TURN server for remote access |
| **WebSocket** | Testing, firewall-restricted environments, simpler deployments | ~100-300ms | Works through standard HTTP ports |

Update your [.env](../config/env.example) file to enable WebSocket transport:

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

## Enabling OpenTelemetry Tracing

OpenTelemetry tracing provides comprehensive observability for your voice agent pipeline, allowing you to monitor performance, debug issues, and analyze conversation flows. The following steps show how to enable tracing with [Phoenix](https://arize.com/docs/phoenix/self-hosting).

1. Add the Phoenix service to the `docker-compose.yml` file as follows.

    ```yaml
    phoenix:
      image: arizephoenix/phoenix:latest
      ports:
        - "6006:6006"  # UI and OTLP HTTP collector
        - "4317:4317"  # OTLP gRPC collector
      restart: unless-stopped
    ```

2. Edit the `.env` file and enable tracing as follows.

    ```bash
    # In .env file
    ENABLE_TRACING=true
    OTEL_CONSOLE_EXPORT=false  # Set to true for console output (useful for debugging)
    OTEL_EXPORTER_OTLP_ENDPOINT=phoenix:4317  # Phoenix OTLP endpoint (gRPC on port 4317)
    ```

    **Configuration Options**:
    - `ENABLE_TRACING`: Set to `true` to enable OpenTelemetry tracing
    - `OTEL_CONSOLE_EXPORT`: Set to `true` to also export traces to console (useful for local debugging)
    - `OTEL_EXPORTER_OTLP_ENDPOINT`: The OTLP endpoint URL for trace export.
      - For **gRPC** (port 4317): Use `host:port` format (e.g., `phoenix:4317` or `localhost:4317`)
      - For **HTTP** (port 4318 or custom): Use `http://host:port` format (e.g., `http://phoenix:4318`)

3. Deploy the services.

    ```bash
    docker compose up -d
    ```

4. Open the Phoenix UI dashboard on your browser.

    ```text
    http://localhost:6006
    ```

    For remote access, use the following URL, replacing `your-server-ip` with your server's public IP address.

    ```text
    http://your-server-ip:6006
    ```

Through the Phoenix UI dashboard, you can:
- View distributed traces from your voice agent pipeline.
- Analyze conversation flows and latency.
- Monitor ASR, LLM, and TTS performance.
- Debug issues with detailed span information.

For alternative tracing backends, refer to the [OpenTelemetry Tracing with Pipecat](https://github.com/pipecat-ai/pipecat-examples/tree/main/open-telemetry) documentation. Note that using different backends might require minor modifications to the `src/pipeline.py` file.

---

## Advanced Configuration Settings

You can set advanced pipeline configurations to optimize the performance and user experience of the Nemotron Voice Agent.

### Speculative Speech Processing

This feature reduces bot response latency by processing interim ASR transcripts instead of waiting for the user to finish speaking and generating the final transcripts.

To enable speculative speech processing, set the `ENABLE_SPECULATIVE_SPEECH` environment variable to `true` in the `.env` file. By default, speculative speech processing is enabled.

```bash
# In .env file
ENABLE_SPECULATIVE_SPEECH=true  # Default: true
```

This feature only works with the NVIDIA Riva ASR NIM microservice. Refer to the [Speculative Speech Processing docs](./05-speculative-speech-processing.md) for details.

### Chat History Limit

To control the conversation context window, set the `CHAT_HISTORY_LIMIT` environment variable to the number of conversation turns to retain in the `.env` file. By default, the conversation context window is set to 20.

```bash
# In .env file
CHAT_HISTORY_LIMIT=20  # Number of conversation turns to retain
```

**Recommendations**:
- **Standard conversations**: 20 (default)
- **Emotion-aware TTS**: 3-5 (better emotion tracking)
- **Multilingual mode**: 3-5 (better language detection)

### Audio Debugging

You can enable raw audio capture for ASR/TTS debugging and issue reproduction.

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_ASR_AUDIO_DUMP` | `false` | Capture incoming user audio |
| `ENABLE_TTS_AUDIO_DUMP` | `false` | Capture outgoing synthesized audio |
| `AUDIO_DUMP_PATH` | `./audio_dumps` | Output directory for WAV files |

To enable audio debugging, set the environment variables as follows in the `.env` file.

```bash
ENABLE_ASR_AUDIO_DUMP=true
ENABLE_TTS_AUDIO_DUMP=true
AUDIO_DUMP_PATH=./audio_dumps # Output directory for WAV files.
```

Output files use WAV format with stream IDs for correlation.

> **Note**: If Docker creates the folder with different permissions, you can fix this in one of two ways:
>- Option 1: Pre-create directory before container start
>    ```bash
>    mkdir -p ./audio_dumps
>    ```
>- Option 2: Fix ownership after container creates it
>    ```bash
>    sudo chown -R $(id -u):$(id -g) ./audio_dumps
>    ```

> **Warning:** Disable audio debugging in production to prevent disk exhaustion.

### Audio Output Buffering

To control audio output latency and stability, set the `AUDIO_OUT_10MS_CHUNKS` environment variable to the number of 10ms chunks to buffer for output. By default, the audio output buffer size is set to 5.

```bash
# In .env file
AUDIO_OUT_10MS_CHUNKS=5  # Number of 10ms chunks to buffer
```

The following are the configuration guidelines for the `AUDIO_OUT_10MS_CHUNKS` environment variable.
- **Default WebRTC**: 5 chunks (50ms buffer) - optimized for low latency
- **Default WebSocket**: 10 chunks (100ms buffer) - more stable for network variations
- **High Concurrency**: 10-40 chunks (100-400ms buffer) - prevents audio glitches under high load
