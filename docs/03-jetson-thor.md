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

    c. Download the Riva Speech Skills v2.26.0 (RC3) Quick Start bundle for L4T (JetPack 7.0) **next to the repo** (not inside it), so the ~30–50 GB model repo survives re-clones and worktrees:

    ```bash
    cd ..
    curl -o riva_quickstart_l4t_aarch64.54633105.tgz \
      -H "PRIVATE-TOKEN:<YOUR_GITLAB_TOKEN>" \
      https://gitlab-master.nvidia.com/api/v4/projects/45235/packages/generic/riva_quickstart/2.26.0/riva_quickstart_l4t_aarch64.54633105.tgz
    tar -xzf riva_quickstart_l4t_aarch64.54633105.tgz
    cd quickstart
    ```

    d. This RC3 bundle already ships with `riva_ngc_org="nvstaging"` and `riva_ngc_model_version="2.26.0"` in `config.sh`, so it pulls the 2.26.0 staging models by default. Confirm (or re-assert) the staging org before initializing:

    ```bash
    sed -i 's/^riva_ngc_org=.*/riva_ngc_org="nvstaging"/' config.sh
    grep -E '^riva_ngc_org|^riva_ngc_model_version' config.sh
    ```

    e. Run only `riva_init.sh` — it downloads the ASR/TTS models and AOT-compiles the TRT engines into `model_repository/`. **Do not run `riva_start.sh`** — the `nemotron-speech` compose service in step 4 will serve the models itself.

    ```bash
    bash riva_init.sh
    cd ../nemotron-voice-agent
    ```

    > **Note:** Initialization may take 30–60 minutes on first run.

    > If the quickstart lives somewhere other than the repo's sibling directory, set `RIVA_MODEL_LOC` in `.env` to the absolute path of `model_repository/`.

4. Start the full stack — vLLM (Nemotron Nano), Riva (ASR + TTS), and the Pipecat pipeline — all via Docker Compose:

    ```bash
    docker compose --profile generic-assistant/jetson-thor up -d
    ```

    > **Note:** First start waits for Riva's ~90 s warmup. Subsequent starts are fast.

    > **Production tuning (recommended on Thor):** CUDA MPS + CPU pinning eliminate audible glitches when vLLM and Riva run in parallel. Set `VLLM_MPS_THREAD_PCT=50`, `RIVA_MPS_THREAD_PCT=50`, `VLLM_CPUSET=0-3`, `RIVA_CPUSET=4-7`, `PIPECAT_CPUSET=8-11` in `.env`, then:
    >
    > ```bash
    > sudo bash scripts/start-mps.sh
    > docker compose --profile generic-assistant/jetson-thor up -d
    > ```

5. Access the application at `https://<jetson-ip>:7860`, or `http://<jetson-ip>:7860` when `PIPELINE_TLS=false`.

    > **Tip:** For the best experience, we recommend using a headset (preferably wired) instead of your laptop's built-in microphone.

    > **Note:** If you need to access the application from remote locations, configure a TURN server. Refer to [Optional: Deploy TURN Server for Remote Access](01-getting-started.md#optional-deploy-turn-server-for-remote-access).

---

## Common Commands

Use the same recipe profile as in step 4.

```bash
# View logs
docker compose --profile generic-assistant/jetson-thor logs -f generic-assistant

# Stop all services
docker compose --profile generic-assistant/jetson-thor down

# Rebuild after code changes
docker compose --profile generic-assistant/jetson-thor up --build -d generic-assistant
```
