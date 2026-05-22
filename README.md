[![Live Demo](https://img.shields.io/badge/Live_Demo-Nemotron_Voice_Chat-76b900?style=for-the-badge&logo=nvidia)](https://10.117.5.80:7860/)

# Nemotron Voice Agent

Nemotron Voice Agent provides a comprehensive, end-to-end voice agent blueprint built with NVIDIA Nemotron state-of-the-art open models, as NVIDIA NIM for acceleration and scaling. It is designed to guide developers through the creation of a cascaded pipeline, integrating Nemotron ASR, LLM, and TTS, while solving for the complexities of streaming, interruptible conversations.

Built on the open-source [Pipecat framework](https://github.com/pipecat-ai/pipecat) and leveraging NVIDIA NIM microservices, this example helps teams accelerate the deployment of high-performance voice AI solutions.

![Architecture Diagram](./docs/images/arch.png)
---

## Key Components

The following are the key components in this blueprint:

- **NVIDIA Nemotron Speech ASR & TTS**: High-performance streaming speech recognition and multilingual text-to-speech synthesis.
  - [Parakeet CTC 1.1B ASR](https://build.nvidia.com/nvidia/parakeet-ctc-1_1b-asr/modelcard)
  - [Nemotron Speech Streaming En 0.6B ASR](https://build.nvidia.com/nvidia/nemotron-speech-streaming-en-0-6b-asr/modelcard)
  - [Parakeet 1.1B RNNT Multilingual ASR](https://build.nvidia.com/nvidia/parakeet-1_1b-rnnt-multilingual-asr/modelcard)
  - [Magpie TTS Multilingual](https://build.nvidia.com/nvidia/magpie-tts-multilingual/modelcard)
- **NVIDIA Nemotron LLMs**: State-of-the-art LLM models engineered for real-time conversational use cases.
  - [Nemotron 3 Nano 30B A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard)
  - [Nemotron 3 Super 120B A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard)
- **NVIDIA Nemotron VoiceChat**: Realtime full duplex speech-to-speech model that jointly performs streaming speech understanding and speech generation. Check [Model Card](https://build.nvidia.com/nvidia/nemotron-voicechat/modelcard) for more details.
- **Pipeline Orchestration**: Built on top of the Pipecat framework with WebRTC and WebSocket transports, enabling low-latency real-time voice communication.

---

## Requirements

Check the following requirements before you begin.

### Hardware Requirements

Pick one **example** profile (which registers the pipeline) and optionally combine with one **hardware** profile (which adds the local NIM/Riva/vLLM sidecars).

| Axis | Profile | Hardware | Services |
|------|---------|----------|----------|
| Example | `cascaded/generic` | None | NVIDIA cloud ASR + LLM + TTS |
| Example | `cascaded/agentic-airline` | None | NVIDIA cloud ASR + LLM + TTS + booking-server sidecar |
| Example | `speech-to-speech/generic` | None | NVIDIA Voice Chat (S2S) over NVCF |
| Hardware | `workstation` | 1 GPU (~80 GB VRAM) | Local NIM ASR + TTS + LLM |
| Hardware | `dgxspark` | 1 GPU, 128 GB unified memory | Local NIM ASR + TTS + vLLM LLM |
| Hardware | `jetson` | 1 GPU, 128 GB unified memory | Local Riva ASR + TTS + vLLM LLM (shared GPU via MPS) |

> Cloud-only is the default — invoking just an example profile uses NVCF services. Add a hardware profile when you want a local stack.

### Software Requirements

- **NVIDIA NGC**: Valid credentials for NVIDIA NGC. See the [NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account).
- **NVIDIA API Key**: Required for NVIDIA NIM models and NGC container images. Get yours at [build.nvidia.com](https://build.nvidia.com/).
- **Docker**: With NVIDIA GPU support installed.

---

## Quick Start

Start the application following these steps.

1. Clone the repository and navigate to the root directory and copy the example environment file [.env.example](.env.example) to the root directory.

    ```bash
    git clone git@github.com:NVIDIA-AI-Blueprints/nemotron-voice-agent.git
    cd nemotron-voice-agent
    cp .env.example .env
    ```

2. Set your NVIDIA API key as an environment variable:

    ```bash
    export NVIDIA_API_KEY=<your-nvidia-api-key>
    ```

3. Login to NVIDIA NGC Docker Registry.

    ```bash
    printf '%s' "$NVIDIA_API_KEY" | docker login nvcr.io -u '$oauthtoken' --password-stdin
    ```

4. Deploy the application.

    ```bash
    docker compose --profile cascaded/generic up -d
    ```

    > **Note:** Deployment may take 30–60 minutes on first run. The example above runs the Generic Cascaded pipeline against NVIDIA cloud APIs. Swap the profile (e.g. `cascaded/agentic-airline`, `speech-to-speech/generic`) to deploy a different example. See the [Getting Started Guide](docs/01-getting-started.md) for on-prem profiles and combining with hardware profiles. Each compose deployment is locked to a single example.

5. Access the application at `https://<machine-ip>:7860`. Set `PIPELINE_TLS=false` in `.env` to use `http://<machine-ip>:7860`.

    > **Note:** Remote clients may need a TURN server for microphone/WebRTC access. See [Optional: Deploy TURN Server for Remote Access](docs/01-getting-started.md#optional-deploy-turn-server-for-remote-access).
    > **Tip:** For the best experience, use a headset, preferably wired.

For detailed setup instructions and troubleshooting, proceed to [Getting Started Guide](docs/01-getting-started.md).

---

## Configuration

The application is configured through these files:

| File | Purpose |
|------|---------|
| `.env` | API keys and feature flags |
| `<example-package>/prompts.yaml` | Example-local persona and system prompt presets selectable from the UI |

Service and prompt catalogs are example-local under each example package, for example
`src/cascaded/generic/services.{cloud,local}.yaml` with
`src/cascaded/generic/prompts.yaml`, or
`src/speech_to_speech/generic/services.cloud.yaml` with
`src/speech_to_speech/generic/prompts.yaml`. The active example (set by the
Docker Compose profile or by `examples_registry.yaml` for host-native runs)
determines which catalogs are loaded.

See the [Configuration Guide](docs/02-configuration-guide.md) for details.

---

## Agent Skills

This repository includes AI agent skills for deployment assistance. Install them for your coding agent with:

```bash
npx skills add .
```

---

## Documentation

| Type | Guide | Description |
|------|-------|-------------|
| Tutorial | [Getting Started](docs/01-getting-started.md) | Full deployment guide with prerequisites, GPU setup, and step-by-step instructions |
| How-to | [Configuration Guide](docs/02-configuration-guide.md) | Configuration guide for `.env`, service YAML catalogs, and prompt catalogs |
| How-to | [Enable Multilingual Voice Agent](docs/how-to/enable-multilingual.md) | Configure prompt-driven multilingual responses with automatic TTS language switching |
| How-to | [Jetson Thor Deployment](docs/03-jetson-thor.md) | Edge deployment guide for NVIDIA Jetson Thor platform |
| How-to | [Tune Pipeline Performance](docs/how-to/tune-pipeline-performance.md) | Smart turn detection, chat history, and transport options |
| How-to | [Enable OpenTelemetry Tracing](docs/how-to/enable-opentelemetry-tracing.md) | Monitor latency and conversation flows with Phoenix or any OTLP backend |
| How-to | [Run Scaling & Performance Tests](docs/how-to/run-scaling-perf-tests.md) | Multi-client latency, throughput, and audio quality benchmarks |
| Explanation | [Best Practices](docs/04-best-practices.md) | Production deployment, latency optimization, and UX design guidelines |
| Reference | [Evaluation and Performance](docs/06-evaluation-and-performance.md) | Accuracy benchmarking and latency/perf tests |

---

## License

This NVIDIA AI BLUEPRINT is licensed under the BSD 2-Clause License. See [LICENSE](LICENSE) for details. This project may download and install additional third-party open source software and containers. Review the license terms of these projects in [third_party_oss_license.txt](third_party_oss_license.txt) before use.
