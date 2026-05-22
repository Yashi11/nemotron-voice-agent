# Getting Started

This guide walks you through deploying the Nemotron Voice Agent on your system.

## Prerequisites

Before you begin, ensure you have the following:

- Access to NVIDIA NGC with valid credentials. Refer to the [NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account).
- Docker with NVIDIA GPU support installed. Refer to the [NIM documentation](https://docs.nvidia.com/nim/riva/asr/latest/getting-started.html#prerequisites).
- NVIDIA API key. Required for accessing NIM ASR, TTS, and LLM models and Docker images. Get yours at [build.nvidia.com](https://build.nvidia.com/).

## GPU Requirements

**Cloud-only mode** (default): No local GPUs required. ASR, LLM, and TTS services run via NVIDIA cloud APIs.

**Docker Compose profiles** (compose freely: pick one **example profile**, optionally combine with one **hardware** profile and any observability profiles):

| Axis | Profile | Hardware | Notes |
|------|---------|----------|-------|
| Example | `cascaded/generic` | None (cloud) | Generic Cascaded pipeline |
| Example | `cascaded/agentic-airline` | None (cloud) | Agentic Airline + booking-server sidecar |
| Example | `speech-to-speech/generic` | None (cloud) | NVIDIA Voice Chat (S2S) |
| Hardware | `workstation` | 1 GPU (≥80 GB VRAM) | NIM ASR + TTS + NIM LLM |
| Hardware | `dgxspark` | 1 GPU, 128 GB unified memory | NIM ASR + TTS + vLLM LLM |
| Hardware | `jetson` | 1 GPU, 128 GB unified memory | Riva ASR + TTS + vLLM LLM (shared GPU via MPS) |
| Observability | `tracing` | — | Phoenix OTel collector |
| Observability | `turn` | — | coturn TURN server |

> Profile names match the registry example keys verbatim. Every deployment specifies exactly one example profile so the deployment intent is unambiguous.

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
    docker compose --profile cascaded/generic up -d            # Generic Cascaded
    docker compose --profile cascaded/agentic-airline up -d    # Agentic Airline (+ booking-server)
    docker compose --profile speech-to-speech/generic up -d    # NVIDIA Voice Chat (S2S)
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
docker compose --profile cascaded/generic --profile workstation up -d

# Generic example — DGX Spark
docker compose --profile cascaded/generic --profile dgxspark up -d

# Generic example — Jetson edge (set HF_TOKEN in .env)
docker compose --profile cascaded/generic --profile jetson up -d

# Agentic Airline example — full local NIM stack on a workstation
docker compose --profile cascaded/agentic-airline --profile workstation up -d
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
docker compose --profile cascaded/generic --profile turn up -d                       # cloud-only + TURN
docker compose --profile cascaded/generic --profile workstation --profile turn up -d # local NIM + TURN
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
