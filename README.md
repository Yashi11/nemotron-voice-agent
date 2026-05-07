[![Live Demo](https://img.shields.io/badge/Live_Demo-Nemotron_Voice_Chat-76b900?style=for-the-badge&logo=nvidia)](https://10.117.5.80:7860/)

# Nemotron Voice Agent

Nemotron Voice Agent provides a comprehensive, end-to-end voice agent blueprint built with NVIDIA Nemotron state-of-the-art open models, as NVIDIA NIM for acceleration and scaling. It is designed to guide developers through the creation of a cascaded pipeline, integrating Nemotron ASR, LLM, and TTS, while solving for the complexities of streaming, interruptible conversations. By leveraging NVIDIA NIM microservices, this developer example enables developers to accelerate the deployment of high-performance voice AI solutions.

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
- **Speech-to-Speech**: Direct voice-to-voice pipeline mode using Nemotron Voice Chat for ultra-low-latency conversations.
- **Pipeline Orchestration**: Built on top of the Pipecat framework with WebRTC and WebSocket transports, enabling low-latency real-time voice communication.

---

## Requirements

Check the following requirements before you begin.

### Hardware Requirements

**Cloud-only mode** (default): No local GPUs required. ASR, LLM, and TTS services run via NVIDIA cloud APIs.

**Local NIM deployment** (optional Docker Compose profiles):

| Profile | Hardware | Services | Description |
|---------|----------|----------|-------------|
| `all-examples` | None (cloud only) | UI selector + booking server | Selector across all registered examples |
| `generic` / `agentic-airline` | None (cloud only) | Single-example backend | Lock the backend to one cloud example |
| `generic-workstation` / `agentic-airline-workstation` | 2 GPUs | GPU 0: ASR + TTS NIMs, GPU 1: NIM LLM | Full local deployment for the chosen example |
| `generic-dgxspark` | 1 GPU, 128 GB unified memory | ASR + TTS NIMs + vLLM LLM | Single-GPU local deployment for the Generic example |
| `generic-jetson` | 1 GPU, 128 GB unified memory | Riva ASR + TTS + vLLM LLM (shared GPU via MPS) | Edge deployment for the Generic example |

### Software Requirements

- **NVIDIA NGC**: Valid credentials for NVIDIA NGC. See the [NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account).
- **NVIDIA API Key**: Required for NVIDIA NIM models and NGC container images. Get yours at [build.nvidia.com](https://build.nvidia.com/). DGX Spark Magpie TTS can use a staging NIM image; ensure `NVIDIA_API_KEY` has access to that image.
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

    For DGX Spark, if you set `TTS_DOCKER_IMAGE` to a staging or private Magpie TTS image, ensure `NVIDIA_API_KEY` has access to that image before logging in.

4. Deploy the application.

    ```bash
    docker compose --profile all-examples up -d
    ```

    > **Note:** Deployment may take 30–60 minutes on first run. The default `all-examples` profile starts the cloud/NVCF selector; see the [Getting Started Guide](docs/01-getting-started.md) for locked examples and on-prem profiles.

5. Access the application at `https://<machine-ip>:7860`.

    > **Note:** Remote clients may need a TURN server for microphone/WebRTC access. See [Optional: Deploy TURN Server for Remote Access](docs/01-getting-started.md#optional-deploy-turn-server-for-remote-access).
    > **Tip:** For the best experience, use a headset, preferably wired.

For detailed setup instructions and troubleshooting, proceed to [Getting Started Guide](docs/01-getting-started.md).

---

## Configuration

The application is configured through these root files:

| File | Purpose |
|------|---------|
| `.env` | API keys, default service selections, and feature flags |
| `services.cloud.yaml` | Cloud (NVCF) service catalog when not using an on-prem platform profile |
| `services.local.yaml` | On-prem catalog used when `DEPLOYMENT_PLATFORM` is set to `workstation`, `dgxspark`, or `jetson` |
| `prompt.yaml` | Persona and system prompt presets selectable from the UI |

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
| How-to | [Configuration Guide](docs/02-configuration-guide.md) | Configuration guide for `.env`, service YAML catalogs, and `prompt.yaml` |
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
