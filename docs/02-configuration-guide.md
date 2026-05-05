# Configuration Guide

The Nemotron Voice Agent is configured through a small set of files at the repository root. Use the following guides to customize specific features.

## Configuration Files

| File | Purpose |
|------|---------|
| [`.env.example`](../.env.example) | API keys, default service selections, and feature flags |
| [`services.cloud.yaml`](../services.cloud.yaml) | Cloud (NVCF) service catalog for plain `docker compose up -d` |
| [`services.local.yaml`](../services.local.yaml) | On-prem catalog used when `DEPLOYMENT_PLATFORM` is set to `workstation`, `dgxspark`, or `jetson` |
| [`prompt.yaml`](../prompt.yaml) | Persona and system prompt presets selectable from the UI |

## How-To Guides

| Guide | Description |
|-------|-------------|
| [Configure Services](./how-to/configure-services.md) | Switch and add LLM, ASR, and TTS services via the UI or YAML catalogs |
| [Configure Prompts](./how-to/configure-prompts.md) | Switch and add prompt presets via the UI or `prompt.yaml` |
| [Enable Multilingual Voice Agent](./how-to/enable-multilingual.md) | Enable prompt-driven multilingual replies with automatic TTS language switching |
| [Configure TTS Settings](./how-to/configure-tts-settings.md) | Set up TTS voice, cloud endpoints, and text filters |
| [Enable Zero-Shot TTS](./how-to/enable-zero-shot-tts.md) | Clone any voice from a short audio sample using the Magpie Zero-shot model |
| [Tune Pipeline Performance](./how-to/tune-pipeline-performance.md) | Smart turn detection, audio debugging, chat history, and transport options |
| [Enable OpenTelemetry Tracing](./how-to/enable-opentelemetry-tracing.md) | Monitor latency, debug issues, and analyze conversation flows with Phoenix or any OTLP backend |
