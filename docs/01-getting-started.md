# Getting Started

This guide walks you through deploying the Nemotron Voice Agent on your system.

## Prerequisites

Before you begin, ensure you have the following:

- Access to NVIDIA NGC with valid credentials. See [NGC Getting Started Guide](https://docs.nvidia.com/ngc/ngc-overview/index.html#registering-activating-ngc-account).
- Docker with NVIDIA GPU support installed. See [NIM documentation](https://docs.nvidia.com/nim/riva/asr/latest/getting-started.html#prerequisites).
- NVIDIA API key. Required for accessing NIM ASR, TTS, and LLM models and docker images. Get yours at [build.nvidia.com](https://build.nvidia.com/).

## GPU Requirements

This blueprint requires **2 NVIDIA GPUs** for running the application:
- One GPU (GPU 0) for running NVIDIA Nemotron Speech ASR (Automatic Speech Recognition) and TTS (Text-to-Speech) models
- One GPU (GPU 1) for running NVIDIA LLM NIM (Large Language Model) for inference

**Note:** GPU requirements may vary depending on your chosen LLM model and available GPU memory.

---

1. Clone the repository and navigate to the root directory of the project.

    ```bash
    git clone git@github.com:NVIDIA-AI-Blueprints/nemotron-voice-agent.git
    cd nemotron-voice-agent
    ```

2. Initialize and update the git submodules.

    ```bash
    git submodule update --init
    ```

3. Configure the environment. To get started, copy the example environment file [.env.example](../config/env.example) to the root directory.

    ```bash
    cp config/env.example .env
    ```

4. Update the `NVIDIA_API_KEY` in the `.env` file with your API keys.

    ```bash
    # Required. Line 13 in .env file.
    NVIDIA_API_KEY=<your-nvidia-api-key>
    ```

5. Login to NVIDIA NGC Docker Registry.

    ```bash
    export NGC_API_KEY=<your-nvidia-api-key>
    docker login nvcr.io
    ```

6. Deploy the application.

    ```bash
    docker compose -f docker-compose.yml up -d
    ```

7. Access the application at `http://<machine-ip>:9000/`

    ![UI Screenshot](./images/ui_webrtc.png)

    **Note:** To enable microphone access in Chrome, go to `chrome://flags/`, enable "Insecure origins treated as secure", add `http://<machine-ip>:9000` to the list, and restart Chrome. To wait for all services to be healthy, check with `docker compose ps`.

---

## Optional: Deploy TURN Server for Remote Access

If you need to access the application from remote locations or deploy on cloud platforms, configure a TURN server following these steps.

1. Set an environment variable for your public IP address.
    ```bash
    export HOST_IP_EXTERNAL=<your-public-ip-address>
    ```

2. Deploy the Coturn server.

    ```bash
    docker run -d --network=host instrumentisto/coturn -n --verbose --log-file=stdout \
      --external-ip=$HOST_IP_EXTERNAL --listening-ip=0.0.0.0 --lt-cred-mech --fingerprint \
      --user=admin:admin --no-multicast-peers --realm=tokkio.realm.org \
      --min-port=51000 --max-port=52000
    ```

3. Update the `.env` file with TURN server configuration.

    ```bash
    # ----------------------------------------------------------------------------
    # TURN SERVER CREDENTIALS
    # ----------------------------------------------------------------------------

    TURN_SERVER_URL=turn:$HOST_IP_EXTERNAL:3478
    TURN_USERNAME=admin
    TURN_PASSWORD=admin
    ```

4. Update WebRTC UI Configuration in the [webrtc_ui](../frontend/webrtc_ui/src/config.ts) file by replacing the empty `RTC_CONFIG` object with your TURN server configuration.

    ```typescript
    // Replace this:
    export const RTC_CONFIG = {};

    // With this:
    export const RTC_CONFIG = {
      iceServers: [
        {
          urls: "turn:$HOST_IP_EXTERNAL:3478",
          username: "admin",
          credential: "admin",
        },
      ],
    };
    ```

    For more information, refer to the [WebRTC TURN Server Documentation](https://webrtc.org/getting-started/turn-server).

5. Restart the Docker Compose services to apply the changes.

    ```bash
    docker compose -f docker-compose.yml up --build -d
    ```
