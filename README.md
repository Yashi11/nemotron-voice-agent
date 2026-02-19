# Nemotron Voice Agent

The Nemotron Voice Agent is a real-time conversational AI system that demonstrates how to build sophisticated voice AI applications using NVIDIA's cutting-edge models and the Pipecat framework. This developer blueprint combines automatic speech recognition (ASR), large language model (LLM) intelligence, and text-to-speech (TTS) to deliver fluid, human-like voice interactions.

![Architecture Diagram](./docs/images/arch.png)

---

## Key Components

The following are the key components in this blueprint:

- **NVIDIA Nemotron Speech ASR & TTS**: High-performance streaming speech recognition (Parakeet CTC 1.1B) paired with multilingual text-to-speech synthesis (Magpie Multilingual).
- **NVIDIA Nemotron LLMs**: State-of-the-art LLM models engineered for real-time conversational use cases.
- **Pipeline Orchestration**: Built on top of the Pipecat framework with WebRTC transport, enabling low-latency real-time voice communication and speculative speech processing capabilities.

---

## Requirements

Check the following requirements before you begin.

### Hardware Requirements

This blueprint requires **2 NVIDIA GPUs** (Ampere, Hopper, Ada, or later).
- **GPU 0**: For running NVIDIA Nemotron Speech ASR (Automatic Speech Recognition) and TTS (Text-to-Speech) models.
- **GPU 1**: For running NVIDIA LLM NIM.

GPU requirements may vary depending on your chosen LLM model and available GPU memory.

### Software Requirements

- **NVIDIA NGC**: Valid credentials for NVIDIA NGC. See the [NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account).
- **NVIDIA API Key**: Required for NVIDIA NIM models and NGC container images. Get yours at [build.nvidia.com](https://build.nvidia.com/).
- **Docker**: With NVIDIA GPU support installed.
- **NVIDIA NIM**: Required for running NVIDIA NIM models. See the [NVIDIA NIM Getting Started Guide](https://docs.nvidia.com/nim/riva/asr/latest/getting-started.html#prerequisites).

---

## Quick Start

Start the application following these steps.

1. Clone the repository and navigate to the root directory and copy the example environment file [.env.example](config/env.example) to the root directory.

    ```bash
    git clone git@github.com:NVIDIA-AI-Blueprints/nemotron-voice-agent.git
    cd nemotron-voice-agent
    git submodule update --init
    cp config/env.example .env
    ```

2. Set your NVIDIA API key as an environment variable:

    ```bash
    export NVIDIA_API_KEY=<your-nvidia-api-key>
    ```

3. Login to NVIDIA NGC Docker Registry.

    ```bash
    export NGC_API_KEY=<your-nvidia-api-key>
    docker login nvcr.io
    ```

4. Deploy the application.

    ```bash
    docker compose up -d
    ```

    > **Note:** Deployment may take 30-60 minutes on first run.

5. Access the application at `http://<machine-ip>:9000/`

For detailed setup instructions, proceed to [Getting Started Guide](docs/01-getting-started.md).

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
| How-to | [Configuration Guide](docs/02-configuration-guide.md) | Configuration guide on the `.env` file depending on various use cases |
| How-to | [Enable Multilingual Voice Agent](docs/how-to/enable-multilingual.md) | Enable multi-language conversations with automatic language detection |
| How-to | [Jetson Thor Deployment](docs/03-jetson-thor.md) | Edge deployment guide for NVIDIA Jetson Thor platform |
| How-to | [Tune Pipeline Performance](docs/how-to/tune-pipeline-performance.md#speculative-speech-processing) | Reduce latency with speculative speech and other performance settings |
| Explanation | [Best Practices](docs/04-best-practices.md) | Production deployment, latency optimization, and UX design guidelines |
| Reference | [NVIDIA Pipecat](docs/05-nvidia-pipecat.md) | Overview of Pipecat services and processors for voice AI pipelines |

## License

TBD

## Disclaimer

TBD
