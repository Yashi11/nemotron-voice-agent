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

    c. Download the Riva Speech Skills v2.26.0 Quick Start bundle for L4T (JetPack 7.0) **next to the repo** (not inside it), so the ~30–50 GB model repo survives re-clones and worktrees:

    ```bash
    cd ..
    ngc registry resource download-version "nvidia/riva/riva_quickstart_arm64:2.26.0"
    cd riva_quickstart_arm64_v2.26.0
    ```

    d. Run only `riva_init.sh` — it downloads the ASR/TTS models and compiles the TRT engines into `model_repository/`. You can check/modify ASR and TTS models to be deployed in `config.sh`. **Do not run `riva_start.sh`** — the `nemotron-speech` compose service in step 4 will serve the models itself.

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

    > **Note:** `PIPELINE_TLS=false` is intended for headless performance and API testing, not interactive browser UI testing. Browser microphone access and WebRTC require a secure context.
    > If you still need HTTP for temporary browser testing, open the browser flags page (for example, `chrome://flags/#unsafely-treat-insecure-origin-as-secure` in Chrome or `edge://flags/#unsafely-treat-insecure-origin-as-secure` in Edge), enable the `Insecure origins treated as secure` flag, add `http://<jetson-ip>:7860`, relaunch the browser, and remove the origin after testing.

    > **Tip:** For the best experience, we recommend using a headset (preferably wired) instead of your laptop's built-in microphone.
    > **Note:** If you need to access the application from remote locations, configure a TURN server. Refer to [Optional: Deploy TURN Server for Remote Access](01-getting-started.md#optional-deploy-turn-server-for-remote-access).

---

## Omni Assistant on Jetson Thor

The Omni Assistant runs **Nemotron 3 Nano Omni** — a single multimodal model that performs ASR and LLM together — locally via vLLM, with Riva serving **TTS only** (Omni handles ASR itself). Thor's 128 GB unified memory fits the 30B NVFP4 model; Orin-class Jetsons are not supported.

Follow **Prerequisites** and **Deployment Steps 1–3** above unchanged — the one-time Riva model build is still required because Riva serves TTS. Then start the Omni recipe instead of the generic one:

```bash
docker compose --profile omni-assistant/jetson-thor up -d
```

This recipe runs three services: `omni-assistant` (app), `nvidia-llm-vllm-omni` (local Omni vLLM), and `nemotron-speech-tts` (Riva TTS).

> **Note:** On first start, the Omni vLLM sidecar downloads `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4` from Hugging Face, so `HF_TOKEN` must be set in `.env`. Allow up to 30 minutes.
> **Production tuning (recommended on Thor):** The same CUDA MPS + CPU pinning settings from step 4 apply. Set the `*_MPS_THREAD_PCT` / `*_CPUSET` values in `.env`, run `sudo bash scripts/start-mps.sh`, then bring up the `omni-assistant/jetson-thor` profile.

The **Common Commands** and **Troubleshooting** sections below also apply — substitute `omni-assistant/jetson-thor` for the recipe profile.

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

---

## Troubleshooting

### Freeing up memory on Jetson Thor

Services can fail to start or behave unexpectedly when the system runs low on available memory — often because cached pages from a previous run are still held by the kernel. A common example is vLLM failing to come up, with the `nvidia-llm-vllm` container logs showing an engine core initialization failure:

```text
(APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above. Failed core proc(s): {}
```

If you hit a low-memory situation, check and reclaim memory before retrying:

1. Check available memory:

    ```bash
    free -h
    ```

2. Free cached memory (drop page cache, dentries, and inodes):

    ```bash
    sudo sync && sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
    ```

3. Re-run `free -h` to confirm available memory has increased, then restart the stack:

    ```bash
    docker compose --profile generic-assistant/jetson-thor up -d
    ```
