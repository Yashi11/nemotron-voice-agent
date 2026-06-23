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
  - [Nemotron ASR Streaming](https://build.nvidia.com/nvidia/nemotron-asr-streaming/modelcard)
  - [Parakeet 1.1B RNNT Multilingual ASR](https://build.nvidia.com/nvidia/parakeet-1_1b-rnnt-multilingual-asr/modelcard)
  - [Magpie TTS Multilingual](https://build.nvidia.com/nvidia/magpie-tts-multilingual/modelcard)
- **NVIDIA Nemotron LLMs**: State-of-the-art LLM models engineered for real-time conversational use cases.
  - [Nemotron 3 Nano 30B A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard)
  - [Nemotron 3 Super 120B A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard)
- **Pipeline Orchestration**: Built on top of the Pipecat framework with WebRTC and WebSocket transports, enabling low-latency real-time voice communication.

---

## Requirements

Check the following requirements before you begin.

### Hardware Requirements

Pick one **recipe** profile. Cloud recipes use `<example>`. On-prem recipes use `<example>/<hardware>`. Each recipe is a complete stack — do not combine separate hardware profiles.

| Profile | Hardware | Services |
|---------|----------|----------|
| `generic-assistant` | None | NVIDIA cloud ASR + LLM + TTS (Generic Assistant) |
| `multilingual-assistant` | None | NVIDIA cloud multilingual ASR + LLM + TTS |
| `omni-assistant` | None | NVIDIA cloud Nemotron Omni (ASR + LLM in one model) + Magpie TTS |
| `omni-assistant-subagents` | None | NVIDIA cloud Nemotron Omni (ASR + LLM in one model) + Magpie TTS, multi-agent with attachments + webcam |
| `thinker-talker` | None | NVIDIA cloud ASR + Talker LLM + Thinker LLM + TTS, plus local booking-server sidecar |
| `generic-assistant/workstation` | 1 GPU (~80 GB VRAM) | Local Nemotron ASR Streaming English + Magpie TTS + LLM |
| `generic-assistant/dgx-spark` | 1 GPU, 128 GB unified memory | Local Nemotron ASR Streaming English + Magpie TTS + vLLM LLM |
| `generic-assistant/jetson-thor` | 1 GPU, 128 GB unified memory | Local Riva ASR + TTS + vLLM LLM (shared GPU via MPS) |
| `multilingual-assistant/workstation` | 1 GPU (~80 GB VRAM) | Local Nemotron ASR Streaming Multilingual + Magpie TTS + LLM |
| `multilingual-assistant/dgx-spark` | 1 GPU, 128 GB unified memory | Local Nemotron ASR Streaming Multilingual + Magpie TTS + vLLM LLM |
| `omni-assistant/workstation` | 1 GPU (~80 GB VRAM) | Local Nemotron Omni vLLM + Magpie TTS |
| `omni-assistant/dgx-spark` | 1 GPU, 128 GB unified memory | Local Nemotron Omni vLLM + Magpie TTS |
| `omni-assistant-subagents/workstation` | 1 GPU (~80 GB VRAM) | Local Nemotron Omni vLLM + Magpie TTS, multi-agent with attachments + webcam |
| `omni-assistant-subagents/dgx-spark` | 1 GPU, 128 GB unified memory | Local Nemotron Omni vLLM + Magpie TTS, multi-agent with attachments + webcam |
| `thinker-talker/workstation` | 1 GPU (~80 GB VRAM) | Local Nemotron ASR Streaming English + TTS + Talker/Thinker LLM, plus local booking-server sidecar |

> Observability profiles (`tracing`, `turn`) can be added alongside any recipe.

### Software Requirements

- **NVIDIA NGC**: Valid credentials for NVIDIA NGC. See the [NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account).
- **NVIDIA API Key**: Required for NVIDIA NIM models and NGC container images. Get yours at [build.nvidia.com](https://build.nvidia.com/).
- **Docker**: With NVIDIA GPU support installed.
- **Docker Compose v2.20 or newer** (`docker compose version`). Required because the root `docker-compose.yml` uses the `include:` directive added in Compose v2.20. Older `docker-compose` v1 (the legacy Python binary) is not supported.

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
    docker compose --profile generic-assistant up -d
    ```

    > **Note:** Deployment may take 30–60 minutes on first run. The example above runs the Generic Cascaded pipeline against NVIDIA cloud APIs. Swap the recipe profile (e.g. `multilingual-assistant`, `thinker-talker`, `generic-assistant/workstation`, `thinker-talker/workstation`) to deploy a different stack. Each compose deployment is locked to a single recipe.

5. Access the application at `https://<machine-ip>:7860`. Keep TLS enabled when testing the browser UI.

    > **Note:** `PIPELINE_TLS=false` is intended for headless performance and API testing, not interactive browser UI testing. Browser microphone access and WebRTC require a secure context; use the default HTTPS UI path for browser validation.
    > If you still need HTTP for temporary browser testing, open the browser flags page (for example, `chrome://flags/#unsafely-treat-insecure-origin-as-secure` in Chrome or `edge://flags/#unsafely-treat-insecure-origin-as-secure` in Edge), enable the `Insecure origins treated as secure` flag, add `http://<machine-ip>:7860`, relaunch the browser, and remove the origin after testing.
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
`src/examples/generic/services.{cloud,local}.yaml` with
`src/examples/generic/prompts.yaml`. The active example (set by the
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
| How-to | [Configure Services](docs/how-to/configure-services.md) | Swap LLM/ASR/TTS models, toggle LLM reasoning, and manage cloud vs local catalogs |
| How-to | [Configure Prompts](docs/how-to/configure-prompts.md) | Author and select per-example system-prompt presets |
| How-to | [Configure TTS Settings](docs/how-to/configure-tts-settings.md) | Voices, languages, pronunciation (IPA), and TTS text filters |
| How-to | [Enable Zero-Shot TTS](docs/how-to/enable-zero-shot-tts.md) | Clone a voice from a short reference sample (planned feature) |
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
