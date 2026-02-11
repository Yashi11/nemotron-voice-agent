# Deploying Voice Agent on Jetson Thor

This guide covers deploying the Nemotron Voice Agent on Jetson Thor using Docker Compose.

---

## Prerequisites

- **Jetson Thor** flashed with **JetPack 7.0** via [NVIDIA SDK Manager](https://developer.nvidia.com/sdk-manager) (with CUDA, CUDA-X, TensorRT, and NVIDIA Container Runtime components installed)
- [NGC CLI](https://org.ngc.nvidia.com/setup/installers/cli) installed and configured
- [Docker Engine](https://docs.docker.com/engine/install/ubuntu/) and [Docker Compose](https://docs.docker.com/compose/install/linux/)
- [HuggingFace API token](https://huggingface.co/docs/hub/en/security-tokens) for downloading LLM models
- Network connectivity

---

## Project Structure

The configuration files for this deployment are the following.

```
./
├── docker-compose.jetson.yml   # Jetson-specific deployment
└── config
    └── env.jetson.example      # Template for .env
```

| File | Purpose |
|------|---------|
| [docker-compose.jetson.yml](../docker-compose.jetson.yml) | Jetson-specific Docker Compose with vLLM |
| [env.jetson.example](../config/env.jetson.example) | Environment template for Jetson deployment |
> **Note:** This deployment uses vLLM for LLM inference instead of NVIDIA NIM. The LLM NIM microservices use TensorRT-LLM which provides optimized, pre-compiled inference engines for specific GPU architectures. Since LLM NIM microservices for Jetson Thor are currently not available, this guide uses vLLM as a flexible alternative to load Hugging Face models directly.

---

## Deployment Steps

1. Clone the repository and navigate to the root directory.

    ```bash
    git clone git@github.com:NVIDIA-AI-Blueprints/nemotron-voice-agent.git
    cd nemotron-voice-agent
    ```

2. Configure the environment. Copy the example environment file [env.jetson.example](../config/env.jetson.example) to the root directory:

    ```bash
    cp config/env.jetson.example .env
    ```

3. Update the `.env` file with your API keys:

    ```bash
    # Required
    NVIDIA_API_KEY=<your-nvidia-api-key>
    HF_TOKEN=<your-huggingface-token>
    ```

    **Jetson-specific defaults** (differ from main deployment):
    - `ENABLE_SPECULATIVE_SPEECH=false` — Disabled for resource optimization.
    - `WORKERS=1` — Single worker to reduce memory usage.

4. Deploy Nemotron Speech ASR and TTS models.

    a. Ensure you meet the [prerequisites](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/quick-start-guide.html#prerequisites) before proceeding.

    b. Configure NGC CLI with your API key:

        ```bash
        ngc config set
        ```

    c. Download and deploy Nemotron Speech ASR and TTS using the Quick Start scripts:

        ```bash
        ngc registry resource download-version nvidia/riva/riva_quickstart_arm64:2.24.0
        cd riva_quickstart_arm64_v2.24.0
        bash riva_init.sh
        bash riva_start.sh
        ```

        > **Note:** Initialization may take 30-60 minutes on first run.

5. Start LLM Service and Voice Agent Application. Start services from the root directory:

    ```bash
    sudo docker compose -f docker-compose.jetson.yml up -d
    ```

6. Access the application at `http://<jetson-ip>:8081` on your browser.

---

## Switching LLM Models

The Jetson deployment uses vLLM to load HuggingFace models. Update these variables in your `.env` file:

| Variable | Description |
|----------|-------------|
| `NVIDIA_LLM_MODEL` | HuggingFace model identifier |
| `GPU_MEMORY_UTILIZATION` | GPU memory fraction (0.0-1.0). Adjust based on model size. |
| `SYSTEM_PROMPT_SELECTOR` | Prompt path from [config/prompt.yaml](../config/prompt.yaml) |

### Available Models

| Model | Size | `GPU_MEMORY_UTILIZATION` |
|-------|------|--------------------------|
| `RedHatAI/Meta-Llama-3.1-8B-Instruct-quantized.w4a16` | 8B (4-bit) | 0.15 |
| `nvidia/Nemotron-Mini-4B-Instruct` | 4B | 0.10 |
| `nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8` | 9B (FP8) | 0.20 |
| `Qwen/Qwen3-4B-Instruct-2507` | 4B | 0.10 |

### Example: Switch to Nemotron-Mini-4B

1. Edit your `.env` file:

    ```bash
    NVIDIA_LLM_MODEL=nvidia/Nemotron-Mini-4B-Instruct
    GPU_MEMORY_UTILIZATION=0.10
    SYSTEM_PROMPT_SELECTOR=llama/flowershop
    ```

2. Restart the services:

    ```bash
    sudo docker compose -f docker-compose.jetson.yml down
    sudo docker compose -f docker-compose.jetson.yml up -d
    ```

3. Verify the model is loading:

    ```bash
    sudo docker compose -f docker-compose.jetson.yml logs -f llm-nvidia-jetson
    ```

> **Note:** The first model download may take several minutes depending on model size and network speed.

---

## Common Commands

```bash
# View logs
sudo docker compose -f docker-compose.jetson.yml logs -f python-app

# Stop all services
sudo docker compose -f docker-compose.jetson.yml down

# Rebuild after code changes
sudo docker compose -f docker-compose.jetson.yml up --build -d python-app
```
