# Nemotron Voice Agent

The Nemotron Voice Agent is a real-time conversational AI system that demonstrates how to build sophisticated conversational AI applications using NVIDIA's cutting-edge AI models and the Pipecat framework. This developer blueprint presents an cascaded voice pipeline combining automatic speech recognition (ASR), large language model (LLM) intelligence, and text-to-speech (TTS) generation to deliver fluid, human-like voice interactions.

## Key Components

- **NVIDIA Riva ASR & TTS**: High-performance streaming speech recognition (Parakeet CTC 1.1B) paired with multilingual text-to-speech synthesis (Magpie Multilingual)
- **NVIDIA Nemotron LLMs**: State-of-the-art LLM models engineered for real-time conversational usecases
- **Pipeline Orchestration**: Built on top of the Pipecat framework with WebRTC transport, enabling low-latency real-time voice communication and speculative speech processing capabilities

This blueprint demonstrates production-ready voice AI functionality, spanning real-time speech processing to sophisticated dialogue management, with full support for containerized deployment at scale.

## QuickStart Guide

### Prerequisites

Before you begin, ensure you have the following:

- Access to NVIDIA NGC with valid credentials. See [NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account)
- NVIDIA GPU (Ampere, Hopper, Ada, or later architecture). See [Support Matrix](https://docs.nvidia.com/nim/riva/asr/latest/support-matrix.html#hardware)
- Docker with NVIDIA GPU support installed. See [NIM documentation](https://docs.nvidia.com/nim/riva/asr/latest/getting-started.html#prerequisites)
- **Required API Keys:** : `NVIDIA_API_KEY` - Required for accessing NIM ASR, TTS, and LLM models and docker images. Get yours at [build.nvidia.com](https://build.nvidia.com/)

### GPU Requirements

This application requires **2 NVIDIA GPUs** by default:
- **GPU 0**: ASR (Automatic Speech Recognition) and TTS (Text-to-Speech) models
- **GPU 1**: LLM (Large Language Model) inference

**Note:** GPU requirements may vary depending on your chosen LLM model and available GPU memory.


### Step 1: Clone and Navigate

```bash
git clone git@github.com:NVIDIA-AI-Blueprints/nemotron-voice-agent.git
cd nemotron-voice-agent
```

Initialize and update the git submodules:

```bash
git submodule update --init
```

### Step 2: Configure Environment

Copy the example environment file to the root directory:

```bash
cp config/env.example .env
```

Update the `.env` file with your API keys:

```bash
# Required
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxx
```

### Step 3: Docker login to nvcr.io

Login to NVIDIA NGC Docker Registry:

```bash
export NGC_API_KEY=nvapi-...
docker login nvcr.io
```
### Step 4: Deploy the Application

Download docker images and start all services:

```bash
docker compose -f docker-compose.yml up -d
```

**Note:** First-time deployment may take 30-45 minutes as Docker builds images and downloads models.

**Alternative: Build from Source**

If you have made local changes to the codebase, use the build option instead:

```bash
docker compose -f docker-compose.yml up --build -d
```


### Step 5: Access the Application

- Wait for all services to be healthy (check with `docker compose ps`)
- Open your browser and navigate to `http://<machine-ip>:9000/`


### Step 6: [Optional] Deploy Coturn Server for Remote Access

If you need to access the application from remote locations or deploy on cloud platforms, you will need to configure a TURN server:

1. Deploy the Coturn server (replace `<HOST_IP_EXTERNAL>` with your public IP):

```bash
docker run -d --network=host instrumentisto/coturn -n --verbose --log-file=stdout \
  --external-ip=<HOST_IP_EXTERNAL> --listening-ip=0.0.0.0 --lt-cred-mech --fingerprint \
  --user=admin:admin --no-multicast-peers --realm=tokkio.realm.org \
  --min-port=51000 --max-port=52000
```

2. Update `.env` with Turn server configuration:

```bash
# ----------------------------------------------------------------------------
# TURN SERVER CREDENTIALS
# ----------------------------------------------------------------------------

TURN_SERVER_URL=turn:<HOST_IP_EXTERNAL>:3478
TURN_USERNAME=admin
TURN_PASSWORD=admin
```

3. Update `webrtc_ui/src/config.ts` with the same configuration:

```typescript
export const RTC_CONFIG: ConstructorParameters<typeof RTCPeerConnection>[0] = {
    iceServers: [
      {
        urls: "turn:<HOST_IP_EXTERNAL>:3478",
        username: "admin",
        credential: "admin",
      },
    ],
  };
```

For more information, see [WebRTC TURN Server Documentation](https://webrtc.org/getting-started/turn-server).

4. Restart the Docker Compose services:
```bash
docker compose -f docker-compose.yml up --build -d
```

### Step 7: Start interacting with the application

![UI Screenshot](./docs/images/ui_webrtc.png)

Note: To enable microphone access in Chrome, go to `chrome://flags/`, enable "Insecure origins treated as secure", add `http://<machine-ip>:9000` to the list, and restart Chrome.

## Agent Skills

This repository includes AI agent skills for deployment assistance. Install them for your coding agent with:

```bash
npx skills add .
```

## Documentation

- [Multilingual Support](docs/MULTILINGUAL.md) - Guide for building voice agents with multilingual capabilities
- [Jetson Thor Deployment](docs/JETSON_THOR.md) - Deployment guide for NVIDIA Jetson Thor edge platform
- [Customization Guide](docs/CUSTOMIZATION_GUIDE.md) - Configuration options for models, prompts, and deployment settings
- [NVIDIA Pipecat](docs/NVIDIA_PIPECAT.md) - Overview of NVIDIA Pipecat services and processors for voice AI pipelines
- [Best Practices](docs/BEST_PRACTICES.md) - Production deployment strategies and performance optimization guidelines
- [Speculative Speech Processing](docs/SPECULATIVE_SPEECH_PROCESSING.md) - Advanced speech processing techniques for reduced latency
- [WebRTC UI](webrtc_ui/README.md) - React-based WebRTC UI for voice agent interactions with microphone access
