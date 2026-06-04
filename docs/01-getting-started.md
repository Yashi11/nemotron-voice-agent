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
| `cascaded-generic` | None (cloud) | Generic Cascaded pipeline (Generic Assistant) |
| `cascaded-multilingual` | None (cloud) | Multilingual Cascaded pipeline |
| `cascaded-omni` | None (cloud) | Nemotron Omni (single-model ASR + LLM) + Magpie TTS |
| `cascaded-thinker-talker` | None (cloud) | Thinker/Talker airline pipeline with local booking-server sidecar |
| `cascaded-generic/workstation` | 1 GPU (>=80 GB VRAM) | NIM ASR + TTS + NIM LLM |
| `cascaded-generic/dgx-spark` | 1 GPU, 128 GB unified memory | NIM ASR + TTS + vLLM LLM |
| `cascaded-generic/jetson-thor` | 1 GPU, 128 GB unified memory | Riva ASR + TTS + vLLM LLM (shared GPU via MPS) |
| `cascaded-multilingual/workstation` | 1 GPU (>=80 GB VRAM) | Parakeet RNNT ASR + Magpie TTS + NIM LLM |
| `cascaded-multilingual/dgx-spark` | 1 GPU, 128 GB unified memory | Parakeet RNNT ASR + Magpie TTS + vLLM LLM |
| `cascaded-omni/workstation` | 1 GPU (>=80 GB VRAM) | Local Nemotron Omni vLLM + Magpie TTS |
| `cascaded-omni/dgx-spark` | 1 GPU, 128 GB unified memory | Local Nemotron Omni vLLM + Magpie TTS |
| `cascaded-thinker-talker/workstation` | 1 GPU (>=80 GB VRAM) | NIM ASR + TTS + Talker/Thinker NIM LLM, plus local booking-server sidecar |
| `tracing` | Optional overlay | Phoenix OTel collector |
| `turn` | Optional overlay | coturn TURN server |

> Every deployment specifies exactly one recipe profile. Observability profiles (`tracing`, `turn`) can be added alongside any recipe. Omni examples support DGX Spark today.

---

## Deployment Steps

1. Clone the repository and navigate to the root directory.

    ```bash
    git clone git@github.com:NVIDIA-AI-Blueprints/nemotron-voice-agent.git
    cd nemotron-voice-agent
    ```

2. Configure the environment. Copy the example environment file [.env.example](../.env.example) to the root directory.

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
    docker compose --profile cascaded-generic up -d         # Generic Cascaded
    docker compose --profile cascaded-multilingual up -d    # Multilingual Cascaded
    docker compose --profile cascaded-omni up -d            # Nemotron Omni Assistant
    docker compose --profile cascaded-thinker-talker up -d  # Thinker/Talker Airline Assistant
    ```

    Pick the profile that matches the pipeline family you want to run. `docker compose up` with no profile is intentionally a no-op so the deployment is always explicit.

    > **Note:** Each Docker Compose profile sets `EXAMPLE_SELECTION=<family>/all`, so the container exposes all examples within that family in the UI selector. To lock to a single example, set environment variable `EXAMPLE_SELECTION=<family>/<example>`.

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
# Generic Cascaded — full local NIM stack on a workstation
docker compose --profile cascaded-generic/workstation up -d

# Generic Cascaded — DGX Spark
docker compose --profile cascaded-generic/dgx-spark up -d

# Generic Cascaded — Jetson Thor edge (set HF_TOKEN in .env)
docker compose --profile cascaded-generic/jetson-thor up -d

# Multilingual Cascaded — workstation (Parakeet RNNT ASR + Magpie TTS + NIM LLM)
docker compose --profile cascaded-multilingual/workstation up -d

# Multilingual Cascaded — DGX Spark
docker compose --profile cascaded-multilingual/dgx-spark up -d

# Omni Assistant — local Omni vLLM + NIM TTS on a workstation
docker compose --profile cascaded-omni/workstation up -d

# Omni Assistant — local Omni vLLM + NIM TTS on DGX Spark
docker compose --profile cascaded-omni/dgx-spark up -d

# Thinker/Talker Airline Assistant — workstation (local NIM ASR / TTS / LLM + booking server)
docker compose --profile cascaded-thinker-talker/workstation up -d
```

List compatible LLM NIM profiles for your hardware:

```bash
docker run --rm --gpus all \
  -e NGC_API_KEY="$NVIDIA_API_KEY" \
  nvcr.io/nim/nvidia/nemotron-3-nano:2.0.5 \
  list-model-profiles
```

Run with just an example profile (e.g., `--profile cascaded-generic`) to stay cloud/NVCF only.

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
    uv run python src/server.py --host 0.0.0.0 --port 7860
    ```

    > **Note:** `src/server.py` defaults to `--host localhost --port 7860`, which only binds the loopback interface. Pass `--host 0.0.0.0 --port 7860` so the UI is reachable from another host (e.g., when accessing `https://<machine-ip>:7860` from a browser on a different machine). Drop the flags only when you intend the server to be reachable from the local machine alone.

    To serve plain HTTP instead of HTTPS, set `PIPELINE_TLS=false` in `.env` or prefix the command:

    ```bash
    PIPELINE_TLS=false uv run python src/server.py --host 0.0.0.0 --port 7860
    ```

    Host-native runs read [`examples_registry.yaml`](../examples_registry.yaml) at the repository root. Edit the `selection` field to choose what the UI exposes, then start the server normally. The server has no example/pipeline CLI flags.

    | `selection` in `examples_registry.yaml` | UI behavior |
    |-----------------------------------------|-------------|
    | `cascaded-generic/all` | Show all Generic Cascaded examples (default) |
    | `cascaded-generic/generic-assistant` | Lock to Generic Assistant |
    | `cascaded-multilingual/all` | Show all Multilingual Cascaded examples |
    | `cascaded-omni/all` | Show all Omni examples |
    | `all` | Show every registered example across all pipeline families |

    After editing, run:

    ```bash
    uv run python src/server.py --host 0.0.0.0 --port 7860
    ```

    > **Note:** Docker Compose deployments set `EXAMPLE_SELECTION=<family>/all` by default, exposing all examples in the family via the UI selector. Override with `EXAMPLE_SELECTION=<family>/<example>` to lock to a single example.

6. Access the application at `https://localhost:7860`, or `http://localhost:7860` when `PIPELINE_TLS=false`.

---

## Optional: Deploy TURN Server for Remote Access

Only needed when the browser connects from a different network than the host (NAT, restrictive firewall, cloud deployment). Localhost and same-subnet clients work without this.

> **Architecture note:** The bundled `turn` profile uses the `instrumentisto/coturn` image, which is supported on **x86_64 (linux/amd64) only**. It is **not** supported on arm64 / aarch64 platforms (for example, NVIDIA Jetson Thor). On arm64 hosts, do not enable `--profile turn`; instead, point the client at an externally hosted TURN server by setting `TURN_URL`, `TURN_USERNAME`, and `TURN_PASSWORD` in `.env` (see the snippet below).

A Coturn service ships in `docker-compose.yml` behind an opt-in `turn` profile. Add `--profile turn` to any deploy command (x86_64 only):

```bash
docker compose --profile cascaded-generic --profile turn up -d              # cloud-only + TURN
docker compose --profile cascaded-generic/workstation --profile turn up -d  # local NIM + TURN
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
