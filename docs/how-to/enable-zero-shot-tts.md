# Enable Zero-Shot TTS

> **Planned Feature** — Zero-shot TTS pipeline integration is not yet available in v2. The steps below outline the intended workflow once support is added.

Zero-shot TTS allows you to clone any voice using a short audio sample (5+ seconds). This feature uses the Magpie Zero-shot model. Apply for access at the [NVIDIA RIVA TTS Zero-shot models page](https://developer.nvidia.com/riva-tts-zeroshot-models).

## Steps

1. Prepare your audio sample to meet the following requirements.
   - Audio format is WAV (16-bit PCM recommended).
   - Audio duration is at least 5 seconds of clean speech.
   - Audio quality is clear, no background noise.
   - Language should match your target language.
   - Speaker is single speaker only.

2. Create the `audio_prompts` directory and add your voice sample.

    ```bash
    mkdir -p audio_prompts
    cp <your_audio_file>.wav audio_prompts/<your_audio_file>.wav
    ```

3. Run the Magpie zero-shot NIM microservice following the instructions in the [NVIDIA NIM RIVA TTS documentation](https://docs.nvidia.com/nim/riva/tts/latest/getting-started.html#launching-the-nim).

4. Add the zero-shot TTS service to the selected example's `services.local.yaml` under the active platform block (or to its `services.cloud.yaml` if you expose it as a built-in cloud entry). Use Compose network names for on-prem entries. The backend rewrites them to `localhost` when the app is run directly on the host:

    ```yaml
    workstation:
      tts:
        magpie-zeroshot:
          name: "Magpie Zero-Shot"
          server: "tts-service:50051"
          voice_id: "Magpie-ZeroShot.Female-1"
          function_id: ""
    ```

5. Select the zero-shot TTS service from the Services tab in the UI, or move its entry to the top of the catalog's `tts:` block to make it the runtime default.

6. Deploy the services with the recipe profile that matches your example and hardware, for example:

    ```bash
    docker compose --profile cascaded-generic/workstation up -d
    ```
