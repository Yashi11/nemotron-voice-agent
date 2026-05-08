# Deploying Voice Agent on Jetson Thor

This guide covers deploying the Nemotron Voice Agent on Jetson Thor using Docker Compose.

---

## Prerequisites

- **Jetson Thor** flashed with **JetPack 7.0** using [NVIDIA SDK Manager](https://developer.nvidia.com/sdk-manager) (with CUDA, CUDA-X, TensorRT, and NVIDIA Container Runtime components installed)
- [NGC CLI](https://org.ngc.nvidia.com/setup/installers/cli) installed and configured
- [Docker Engine](https://docs.docker.com/engine/install/ubuntu/) and [Docker Compose](https://docs.docker.com/compose/install/linux/)
- [HuggingFace API token](https://huggingface.co/docs/hub/en/security-tokens) for downloading LLM models
- Network connectivity

---

## Deployment Steps

1. Clone the repository and configure the environment:

    ```bash
    git clone git@github.com:NVIDIA-AI-Blueprints/nemotron-voice-agent.git
    cd nemotron-voice-agent
    cp .env.example .env
    ```

2. Set your API keys in the `.env` file:

    ```bash
    # Required
    NVIDIA_API_KEY=<your-nvidia-api-key>
    HF_TOKEN=<your-huggingface-token>
    ```

3. Build the Nemotron Speech (Riva) model repository. **One-time per machine.**

    a. Ensure you meet the [prerequisites](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/quick-start-guide.html#prerequisites) before proceeding.

    b. Configure NGC CLI with your API key:

    ```bash
    ngc config set
    ```

    c. Download the Riva Quick Start bundle **next to the repo** (not inside it), so the ~30–50 GB model repo survives re-clones and worktrees:

    ```bash
    cd ..
    ngc registry resource download-version nvidia/riva/riva_quickstart_arm64:2.24.0
    cd riva_quickstart_arm64_v2.24.0
    ```

    d. Run only `riva_init.sh` — it downloads the ASR/TTS models and AOT-compiles the TRT engines into `model_repository/`. **Do not run `riva_start.sh`** — the `nemotron-speech` compose service in step 4 will serve the models itself.

    ```bash
    bash riva_init.sh
    cd ../nemotron-voice-agent
    ```

    > **Note:** Initialization may take 30–60 minutes on first run.

    > If the quickstart lives somewhere other than the repo's sibling directory, set `RIVA_MODEL_LOC` in `.env` to the absolute path of `model_repository/`.

4. Start the full stack — vLLM (Nemotron Nano), Riva (ASR + TTS), and the Pipecat pipeline — all via Docker Compose:

    ```bash
    docker compose --profile generic-jetson up -d
    ```

    > **Note:** First start waits for Riva's ~90 s warmup. Subsequent starts are fast.

    > **Production tuning (recommended on Thor):** CUDA MPS + CPU pinning eliminate audible glitches when vLLM and Riva run in parallel. Set `VLLM_MPS_THREAD_PCT=50`, `RIVA_MPS_THREAD_PCT=50`, `VLLM_CPUSET=0-3`, `RIVA_CPUSET=4-7`, `PIPECAT_CPUSET=8-11` in `.env`, then:
    >
    > ```bash
    > sudo bash scripts/start-mps.sh
    > docker compose --profile generic-jetson up -d
    > ```

5. Access the application at `https://<jetson-ip>:7860`.

    > **Tip:** For the best experience, we recommend using a headset (preferably wired) instead of your laptop's built-in microphone.

    > **Note:** If you need to access the application from remote locations, configure a TURN server. Refer to [Optional: Deploy TURN Server for Remote Access](01-getting-started.md#optional-deploy-turn-server-for-remote-access).

---

## Common Commands

Use the same profile as in step 4.

```bash
# View logs
docker compose --profile generic-jetson logs -f generic-example-jetson

# Stop all services
docker compose --profile generic-jetson down

# Rebuild after code changes
docker compose --profile generic-jetson up --build -d generic-example-jetson
```
