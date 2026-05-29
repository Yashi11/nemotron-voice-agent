# Getting Started

This guide walks you through deploying the Nemotron Voice Agent on your system.

## Prerequisites

Before you begin, ensure you have the following:

- Access to NVIDIA NGC with valid credentials. Refer to the [NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account).
- Docker with NVIDIA GPU support installed. Refer to the [NIM documentation](https://docs.nvidia.com/nim/riva/asr/latest/getting-started.html#prerequisites).
- Docker Compose v2.20 or newer (`docker compose version`). The root `docker-compose.yml` uses the `include:` directive added in Compose v2.20. Legacy `docker-compose` v1 (the Python binary) is not supported.
- NVIDIA API key. Required for accessing NIM ASR, TTS, and LLM models and Docker images. Get yours at [build.nvidia.com](https://build.nvidia.com/).

## GPU Requirements

**Cloud-only mode** (default): No local GPUs required. ASR, LLM, and TTS services run via NVIDIA cloud APIs.

**Docker Compose recipes** (pick one **recipe profile**. Optionally combine with one or more observability profiles):

| Profile | Hardware | Notes |
|---------|----------|-------|
| `cascaded/generic` | None (cloud) | Generic Cascaded pipeline |
| `cascaded/agentic-airline` | None (cloud) | Agentic Airline + booking-server sidecar |
| `cascaded/omni-assistant` | None (cloud) | Nemotron Omni (single-model ASR + LLM) + Magpie TTS |
| `cascaded/omni-assistant-subagents` | None (cloud) | Omni Assistant with media analyzer + webcam vision subagents |
| `speech-to-speech/generic` | None (cloud) | NVIDIA Voice Chat (S2S) |
| `cascaded/generic/workstation` | 1 GPU (>=80 GB VRAM) | NIM ASR + TTS + NIM LLM |
| `cascaded/generic/dgxspark` | 1 GPU, 128 GB unified memory | NIM ASR + TTS + vLLM LLM |
| `cascaded/generic/jetson` | 1 GPU, 128 GB unified memory | Riva ASR + TTS + vLLM LLM (shared GPU via MPS) |
| `cascaded/agentic-airline/workstation` | 1 GPU (>=80 GB VRAM) | Agentic Airline with local NIM ASR + TTS + LLM |
| `cascaded/omni-assistant/workstation` | 1 GPU (>=80 GB VRAM) | Local Nemotron Omni vLLM + Magpie TTS |
| `cascaded/omni-assistant/dgxspark` | 1 GPU, 128 GB unified memory | Local Nemotron Omni vLLM + Magpie TTS |
| `cascaded/omni-assistant-subagents/dgxspark` | 1 GPU, 128 GB unified memory | Subagents with local Nemotron Omni vLLM + Magpie TTS |
| `tracing` | Optional overlay | Phoenix OTel collector |
| `turn` | Optional overlay | coturn TURN server |

> Every deployment specifies exactly one recipe profile. Observability profiles (`tracing`, `turn`) can be added alongside any recipe. Omni examples support DGX Spark today. Jetson is not yet supported because the 30B Omni NVFP4 model does not fit on Orin-class hardware.

---

## Deployment Steps

1. Clone the repository and navigate to the root directory.

    ```bash
    git clone git@github.com:NVIDIA-AI-Blueprints/nemotron-voice-agent.git
    cd nemotron-voice-agent
    ```

2. Configure the environment. Copy the example environment file [.env.example](.env.example) to the root directory.

    ```bash
    cp .env.example .env
    ```

3. Set your NVIDIA API key as an environment variable:

    ```bash
    export NVIDIA_API_KEY=<your-nvidia-api-key>
    ```

4. Log in to the NVIDIA NGC Docker Registry.

    ```bash
    printf '%s' "$NVIDIA_API_KEY" | docker login nvcr.io -u '$oauthtoken' --password-stdin
    ```

    For DGX Spark staging or private Magpie TTS images, ensure `NVIDIA_API_KEY` has access before logging in.

5. Deploy a cloud-only example:

    ```bash
    docker compose --profile cascaded/generic up -d                       # Generic Cascaded
    docker compose --profile cascaded/agentic-airline up -d               # Agentic Airline (+ booking-server)
    docker compose --profile cascaded/omni-assistant up -d                # Nemotron Omni Assistant
    docker compose --profile cascaded/omni-assistant-subagents up -d      # Omni Assistant with subagents
    docker compose --profile speech-to-speech/generic up -d               # NVIDIA Voice Chat (S2S)
    ```

    Pick the example profile that matches the registry key you want to run. `docker compose up` with no profile is intentionally a no-op so the deployment is always explicit.

    > **Note:** Docker Compose deployments are per-example only — pick the profile that matches the example you want to run. Selector mode (one container exposing multiple examples in the UI) is supported for host-native runs only (see [Local Development](#optional-local-development-without-docker)).

    > **Note:** Deployment may take 30–60 minutes on first run.

6. Access the application at `https://<machine-ip>:7860`.
   HTTPS is enabled by default. Set `PIPELINE_TLS=false` in `.env` to serve plain HTTP at `http://<machine-ip>:7860`.

    > **Tip:** For the best experience, we recommend using a headset (preferably wired) instead of your laptop's built-in microphone.

    To verify all services are healthy, run `docker compose ps`.

---

## Optional: Deploy with Local NIM Profiles

Local NIM ASR/TTS/LLM sidecars run alongside the example container when you launch a local profile. The backend exposes them automatically once the containers are reachable. No extra `.env` flag is required.

> **OOM troubleshooting:** If the LLM process is killed, the NIM/vLLM runtime reports model-load or OOM errors, or latency degrades under load, use separate GPUs when available. On a two-GPU host, place ASR/TTS on one GPU and the LLM on the other. Otherwise, reduce KV cache / context length (lower memory, less long-context capacity). Lowering batch size or precision can also help. Confirm `NVIDIA_API_KEY` and `HF_TOKEN` are set where required so auth failures are not mistaken for OOM.

Workstation profiles place ASR, TTS, and LLM on one GPU by default. Single-GPU deployments are supported only when at least 80 GB of VRAM is available.

DGX Spark and Jetson additionally need `HF_TOKEN` for the vLLM model download. If the Magpie TTS image is staging or private, use a `NVIDIA_API_KEY` with access to that image.

```bash
# Generic example — full local NIM stack on a workstation
docker compose --profile cascaded/generic/workstation up -d

# Generic example — DGX Spark
docker compose --profile cascaded/generic/dgxspark up -d

# Generic example — Jetson edge (set HF_TOKEN in .env)
docker compose --profile cascaded/generic/jetson up -d

# Agentic Airline example — full local NIM stack on a workstation
docker compose --profile cascaded/agentic-airline/workstation up -d

# Omni Assistant — local Omni vLLM + NIM TTS on a workstation
docker compose --profile cascaded/omni-assistant/workstation up -d

# Omni Assistant — local Omni vLLM + NIM TTS on DGX Spark
docker compose --profile cascaded/omni-assistant/dgxspark up -d

# Omni Assistant Subagents — local Omni vLLM + NIM TTS on DGX Spark
docker compose --profile cascaded/omni-assistant-subagents/dgxspark up -d
```

List compatible LLM NIM profiles for your hardware:

```bash
docker run --rm --gpus all \
  -e NGC_API_KEY="$NVIDIA_API_KEY" \
  nvcr.io/nim/nvidia/nemotron-3-nano:1.7.0-variant \
  list-model-profiles
```

Run with just an example profile (e.g., `--profile cascaded/generic`) to stay cloud/NVCF only.

For Jetson-specific setup, refer to [Jetson Thor Deployment](03-jetson-thor.md).

---

## Optional: Local Development (without Docker)

For development and debugging, you can run the server directly:

1. Install [uv](https://docs.astral.sh/uv/) and Node.js 20+.

2. Install dependencies and build the client:

    ```bash
    uv sync --group dev
    cd client && npm install && npm run build && cd ..
    ```

3. Install local commit hooks:

    ```bash
    uv run --project . --group dev pre-commit install
    ```

    The hooks run formatting and linting checks on staged files during `git commit`.

4. Configure the environment:

    ```bash
    cp .env.example .env
    # Edit .env and set NVIDIA_API_KEY
    ```

5. Start the server:

    ```bash
    uv run python src/server.py
    ```

    To serve plain HTTP instead of HTTPS, set `PIPELINE_TLS=false` in `.env` or prefix the command:

    ```bash
    PIPELINE_TLS=false uv run python src/server.py
    ```

    Host-native runs read [`examples_registry.yaml`](../examples_registry.yaml) at the repository root. Edit the `selection` field to choose what the UI exposes, then start the server normally. The server has no example/pipeline CLI flags.

    | `selection` in `examples_registry.yaml` | UI behavior |
    |-----------------------------------------|-------------|
    | `cascaded/generic` | Lock to the Generic Cascaded example |
    | `cascaded/agentic-airline` | Lock to Agentic Airline |
    | `cascaded/omni-assistant` | Lock to Nemotron Omni Assistant |
    | `cascaded/omni-assistant-subagents` | Lock to Omni Assistant Subagents |
    | `speech-to-speech/generic` | Lock to NVIDIA Voice Chat (S2S) |
    | `cascaded/all` | Show every Cascaded example in the UI selector |
    | `all` | Show every registered example across all pipeline families |

    After editing, run:

    ```bash
    uv run python src/server.py
    ```

    > **Note:** Docker Compose deployments ignore the `selection` field — the per-example profile pins each container to a single example. Selector modes (`*/all`, `all`) are host-native only today.

6. Access the application at `https://localhost:7860`, or `http://localhost:7860` when `PIPELINE_TLS=false`.

---

## Optional: Deploy TURN Server for Remote Access

Only needed when the browser connects from a different network than the host (NAT, restrictive firewall, cloud deployment). Localhost and same-subnet clients work without this.

A Coturn service ships in `docker-compose.yml` behind an opt-in `turn` profile. Add `--profile turn` to any deploy command:

```bash
docker compose --profile cascaded/generic --profile turn up -d              # cloud-only + TURN
docker compose --profile cascaded/generic/workstation --profile turn up -d  # local NIM + TURN
```

- Coturn binds host ports UDP `3478` and UDP `49160-49200`. These must be reachable from clients (open them on your cloud firewall / security group).
- The client auto-fetches ICE config from `GET /api/ice-servers` — no client-side setup needed.
- Default credentials are `admin:admin`. For production, override in `.env`:

    ```env
    # Required when TURN is deployed on a different host than all-examples.
    TURN_URL=turn:<turn-host-or-ip>:3478
    TURN_USERNAME=<user>
    TURN_PASSWORD=<pass>
    ```

- If `TURN_URL` is unset, the app derives the TURN host from the request. When using a reverse proxy in that mode, ensure it forwards the `X-Forwarded-Host` header so the derived TURN URL resolves to the client-reachable hostname.
