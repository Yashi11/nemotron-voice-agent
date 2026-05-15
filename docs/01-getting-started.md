# Getting Started

This guide walks you through deploying the Nemotron Voice Agent on your system.

## Prerequisites

Before you begin, ensure you have the following:

- Access to NVIDIA NGC with valid credentials. Refer to the [NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account).
- Docker with NVIDIA GPU support installed. Refer to the [NIM documentation](https://docs.nvidia.com/nim/riva/asr/latest/getting-started.html#prerequisites).
- NVIDIA API key. Required for accessing NIM ASR, TTS, and LLM models and Docker images. Get yours at [build.nvidia.com](https://build.nvidia.com/).

## GPU Requirements

**Cloud-only mode** (default): No local GPUs required. ASR, LLM, and TTS services run via NVIDIA cloud APIs.

**Docker Compose profiles**:

| Profile | Hardware | Services | Description |
|---------|----------|----------|-------------|
| `all-examples` | None (cloud only) | UI selector + booking server | Selector across all registered examples |
| `generic` / `agentic-airline` | None (cloud only) | Single-example backend | Lock the backend to one cloud example |
| `generic-workstation` / `agentic-airline-workstation` | 2 GPUs | GPU 0: ASR + TTS NIMs, GPU 1: NIM LLM | Full local deployment for the chosen example |
| `generic-dgxspark` | 1 GPU, 128 GB unified memory | ASR + TTS NIMs + vLLM LLM | Single-GPU local deployment for the Generic example |
| `generic-jetson` | 1 GPU, 128 GB unified memory | Riva ASR + TTS + vLLM LLM (shared GPU via MPS) | Edge deployment for the Generic example |

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

5. Deploy the default selector application:

    ```bash
    docker compose --profile all-examples up -d
    ```

    This starts one UI/backend plus the Agentic Airline booking server using cloud/NVCF services. Use the UI pipeline selector to switch between registered examples.

    Standalone cloud profiles are also available when you want to lock the backend to one example:

    ```bash
    docker compose --profile generic up -d
    docker compose --profile agentic-airline up -d
    ```

    > **Note:** Deployment may take 30–60 minutes on first run.

6. Access the application at `https://<machine-ip>:7860`.
   HTTPS is enabled by default. Set `PIPELINE_TLS=false` in `.env` to serve plain HTTP at `http://<machine-ip>:7860`.

    > **Tip:** For the best experience, we recommend using a headset (preferably wired) instead of your laptop's built-in microphone.

    To verify all services are healthy, run `docker compose ps`.

---

## Optional: Deploy with Local NIM Profiles

Local NIM ASR/TTS/LLM sidecars run alongside the example container when you launch a local profile. The backend exposes them automatically once the containers are reachable; no extra `.env` flag is required.

DGX Spark and Jetson additionally need `HF_TOKEN` for the vLLM model download. If the Magpie TTS image is staging or private, use a `NVIDIA_API_KEY` with access to that image.

```bash
# Generic example — full local deployment (2 GPUs required)
docker compose --profile generic-workstation up -d

# Generic example — DGX Spark
docker compose --profile generic-dgxspark up -d

# Generic example — Jetson edge (set HF_TOKEN in .env)
docker compose --profile generic-jetson up -d

# Agentic Airline example — full local deployment (2 GPUs required)
docker compose --profile agentic-airline-workstation up -d
```

Run with `--profile generic` (or `--profile agentic-airline`) to stay cloud/NVCF only.

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

    Local server modes:

    | Command | UI behavior |
    |---------|-------------|
    | `uv run python src/server.py` | Select between the default example for each pipeline family (`cascaded/generic`, `speech-to-speech/generic`) |
    | `uv run python src/server.py --all-examples` | Select any registered example, including `cascaded/agentic-airline` |
    | `uv run python src/server.py --example cascaded/agentic-airline` | Lock the server to one example |

6. Access the application at `https://localhost:7860`, or `http://localhost:7860` when `PIPELINE_TLS=false`.

---

## Optional: Deploy TURN Server for Remote Access

Only needed when the browser connects from a different network than the host (NAT, restrictive firewall, cloud deployment). Localhost and same-subnet clients work without this.

A Coturn service ships in `docker-compose.yml` behind an opt-in `turn` profile. Add `--profile turn` to any deploy command:

```bash
docker compose --profile generic --profile turn up -d               # cloud-only + TURN
docker compose --profile generic-workstation --profile turn up -d   # any local profile + TURN
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

- If `TURN_URL` is unset, `all-examples` derives the TURN host from the request. When using a reverse proxy in that mode, ensure it forwards the `X-Forwarded-Host` header so the derived TURN URL resolves to the client-reachable hostname.
