# Deploying Voice Agent on Jetson Thor

This guide covers deploying the NVIDIA Voice Agent on Jetson Thor using Docker Compose.

## Prerequisites

- **Jetson Thor** flashed with **JetPack 7.1** via [NVIDIA SDK Manager](https://developer.nvidia.com/sdk-manager) (with CUDA, CUDA-X, TensorRT, and NVIDIA Container Runtime components installed)
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

### Download and Initialize Riva

> **Note:** Riva for Jetson Thor is available through NVIDIA's Early Access (EA) program.
> Contact your NVIDIA representative to request access to the `ea-riva` NGC organization:
> https://registry.ngc.nvidia.com/orgs/ea-riva/teams/edge/containers/riva-speech

Once you have access, configure NGC CLI with your API key and select `ea-riva` org:

```bash
ngc config set
```

Then download and initialize Riva:

```bash
ngc registry resource download-version ea-riva/edge/riva_quickstart_arm64:1.3-thor-speech-tegra-thor
cd riva_quickstart_arm64_v1.3-thor-speech-tegra-thor
bash riva_init.sh
bash riva_start.sh
```

> **Note:** Riva initialization may take 30-60 minutes on first run.

> **Important:** If the Riva container fails to start (shows "Created" but not "Running"), you may need to fix the GPU runtime flag in `riva_start.sh`:
> ```bash
> # Change --gpus flag to --runtime=nvidia (line ~104 in riva_start.sh)
> sed -i "s/--gpus '\"'\$gpus_to_use'\"'/--runtime=nvidia/" riva_start.sh
> bash riva_start.sh
> ```
> This is required because Jetson uses `--runtime=nvidia` instead of `--gpus` for GPU access.

## Step 5: Start LLM Service and Voice Agent Application

```bash
cd /home/nvidia/voice-agent-examples/examples/voice_agent_webrtc

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
