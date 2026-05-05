# Tune Pipeline Performance

This section covers pipeline configurations for optimizing the performance and user experience of the Nemotron Voice Agent.

- [Smart Turn Detection](#smart-turn-detection)
- [Audio Debugging](#audio-debugging)
- [Chat History Limit](#chat-history-limit)
- [Audio Output Buffering](#audio-output-buffering)
- [Transport Selection](#transport-selection)

## Smart Turn Detection

The cascaded pipeline uses smart turn detection (`LocalSmartTurnAnalyzerV3`) to determine when the user has finished speaking, reducing unnecessary silence waiting before generating a response.

### How It Works

1. User speaks. ASR generates interim transcripts as audio is processed.
2. Smart turn analysis evaluates the transcript context and audio signals to predict end-of-utterance.
3. Once a turn boundary is detected, the pipeline sends the transcript to the LLM for response generation.
4. TTS synthesizes and streams back the response.

### Key Components

| Component | Purpose |
|-----------|---------|
| `SileroVADAnalyzer` | Voice activity detection with configurable silence threshold |
| `LocalSmartTurnAnalyzerV3` | ML-based end-of-utterance detection for natural turn-taking |
| `InterimAwareTurnStopStrategy` | Coordinates turn detection with interim ASR transcripts |

## Audio Debugging

Enable raw audio capture for ASR/TTS debugging and issue reproduction. Each conversation turn is saved as a separate WAV file for easy analysis.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_ASR_AUDIO_DUMP` | `false` | Capture incoming user audio (per turn) |
| `ENABLE_TTS_AUDIO_DUMP` | `false` | Capture outgoing synthesized audio (per turn) |
| `AUDIO_DUMP_PATH` | `audio_dumps/cascaded` | Output directory (relative to project root, or absolute) |

To enable audio debugging, set the environment variables in the `.env` file:

```bash
ENABLE_ASR_AUDIO_DUMP=true
ENABLE_TTS_AUDIO_DUMP=true
AUDIO_DUMP_PATH=audio_dumps/cascaded
```

### Output Format

Files are saved as 16-bit mono PCM WAV with per-turn indexing:

```
audio_dumps/cascaded/
├── asr_<stream_id>_000.wav   # User turn 0
├── asr_<stream_id>_001.wav   # User turn 1
├── tts_<stream_id>_000.wav   # Bot turn 0
├── tts_<stream_id>_001.wav   # Bot turn 1
└── ...
```

The `<stream_id>` is a unique 8-character hex ID per session, so files from concurrent sessions don't collide.

> **Note:** If Docker creates the folder with different permissions, fix ownership:
>
> ```bash
> # Option 1: Pre-create directory before container start
> mkdir -p ./audio_dumps/cascaded
>
> # Option 2: Fix ownership after container creates it
> sudo chown -R $(id -u):$(id -g) ./audio_dumps
> ```

> **Warning:** Disable audio debugging in production to prevent disk exhaustion.

## Chat History Limit

Controls the cascaded pipeline conversation window size. Older messages are dropped using a
sliding window while preserving the initial prompt messages.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_HISTORY_RECENT_TURNS` | `20` | Number of most recent non-prompt messages to keep |

```bash
CHAT_HISTORY_RECENT_TURNS=20
```

### How It Works

When the message count exceeds `CHAT_HISTORY_RECENT_TURNS`, the cascaded pipeline trims context with a
sliding window:

1. Initial prompt messages loaded at session start are always preserved.
2. From all later messages, only the latest `CHAT_HISTORY_RECENT_TURNS` messages are kept.
3. Older non-prompt messages are removed.

### Recommendations

| Use Case | Value |
|----------|-------|
| Standard conversations | `20` (default) |
| Multilingual mode | `3-5` |
| Long-form sessions | `30-50` |

## Audio Output Buffering

To control audio output latency and stability for the cascaded pipeline, set the `AUDIO_OUT_10MS_CHUNKS` environment variable to the number of 10ms chunks to buffer for output. By default, the cascaded pipeline uses `5` for WebRTC and `10` for FastAPI WebSocket.

```bash
# In .env file
AUDIO_OUT_10MS_CHUNKS=10  # Override transport defaults
```

The following are the configuration guidelines for the `AUDIO_OUT_10MS_CHUNKS` environment variable.
- **Default WebRTC**: 5 chunks (50ms buffer) - optimized for low latency
- **Default WebSocket**: 10 chunks (100ms buffer) - more stable for network variations
- **High Concurrency**: 10-40 chunks (100-400ms buffer) - prevents audio glitches under high load

## Transport Selection

The server supports both WebRTC and WebSocket transports simultaneously on different endpoints:

| Transport | Endpoint | Best For |
|-----------|----------|----------|
| **WebRTC** | `POST /api/offer` | Production voice interactions, lowest latency (~50-150ms) |
| **WebSocket** | `WS /api/ws` | Testing, firewall-restricted environments, simpler deployments (~100-300ms) |

The client UI automatically selects the transport. Both are available without any configuration changes.
