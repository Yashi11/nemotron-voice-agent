# Deploying Voice Agent on Jetson Thor

This guide covers deploying the NVIDIA Voice Agent on Jetson Thor using Docker Compose.

## Prerequisites

- **Jetson Thor** flashed with **JetPack 7.0** via [NVIDIA SDK Manager](https://developer.nvidia.com/sdk-manager) (with CUDA, CUDA-X, TensorRT, and NVIDIA Container Runtime components installed)
- [NGC CLI](https://org.ngc.nvidia.com/setup/installers/cli) installed and configured
- [Docker Engine](https://docs.docker.com/engine/install/ubuntu/) and [Docker Compose](https://docs.docker.com/compose/install/linux/)
- [HuggingFace API token](https://huggingface.co/docs/hub/en/security-tokens) for downloading LLM models
- Network connectivity

## Project Structure

```
./
├── docker-compose.jetson.yml   # Jetson-specific deployment
└── config
    └── env.jetson.example          # Template for .env
```
> **Note:** This deployment uses vLLM for LLM inference instead of NVIDIA NIM. NIMs use TensorRT-LLM which provides optimized, pre-compiled inference engines for specific GPU architectures. Since Jetson Thor NIMs are not yet available, vLLM serves as a flexible alternative that can load HuggingFace models directly. Once Jetson Thor NIMs are released, they can be swapped in for improved inference performance.

## Step 1: Clone and Navigate

```bash
git clone git@github.com:NVIDIA-AI-Blueprints/nemotron-voice-agent.git
cd nemotron-voice-agent
```

### Step 2: Configure Environment

Copy the example environment file to the root directory:

```bash
cp config/env.jetson.example .env
```

Update the `.env` file with your API keys:

```bash
# Required
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxx
HF_TOKEN=xxxxxxx
```

## Step 4: Deploy Riva ASR/TTS

Riva provides the speech recognition (ASR) and text-to-speech (TTS) capabilities.

### Prerequisites

Ensure you meet the Riva prerequisites before proceeding:
https://docs.nvidia.com/deeplearning/riva/user-guide/docs/quick-start-guide.html#prerequisites

### Download and Initialize Riva

Configure NGC CLI with your API key:

```bash
ngc config set
```

Download Riva using the Quick Start scripts:

```bash
ngc registry resource download-version nvidia/riva/riva_quickstart_arm64:2.24.0
cd riva_quickstart_arm64_v2.24.0
bash riva_init.sh
bash riva_start.sh
```

> **Note:** Riva initialization may take 30-60 minutes on first run.

## Step 5: Start LLM Service and Voice Agent Application

Start services from the root directory

```bash
sudo docker compose -f docker-compose.jetson.yml up -d
```

## Step 6: Access the Application

Open in browser: `http://<jetson-ip>:8081`

## Switching LLM Models

Available models:

| NVIDIA_LLM_MODEL |
|------------------|
| `RedHatAI/Meta-Llama-3.1-8B-Instruct-quantized.w4a16` |
| `nvidia/Nemotron-Mini-4B-Instruct` |
| `nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8` |
| `Qwen/Qwen3-4B-Instruct-2507` |

To switch:

```bash
# Update NVIDIA_LLM_MODEL in .env
nano .env

# Restart all services (no rebuild needed for model changes)
sudo docker compose -f docker-compose.jetson.yml down
sudo docker compose -f docker-compose.jetson.yml up -d

# Check LLM logs to verify new model is loading
sudo docker compose -f docker-compose.jetson.yml logs -f llm-nvidia-jetson
```

## Common Commands

```bash
# View logs
sudo docker compose -f docker-compose.jetson.yml logs -f python-app

# Stop all services
sudo docker compose -f docker-compose.jetson.yml down

# Rebuild after code changes
sudo docker compose -f docker-compose.jetson.yml up --build -d python-app
```
