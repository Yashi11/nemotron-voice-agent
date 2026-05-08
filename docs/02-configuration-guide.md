# Configuration Guide

The Nemotron Voice Agent is configured through a small set of example-local files plus root `.env` settings. Use the following guides to customize specific features.

## Configuration Files

| File | Purpose |
|------|---------|
| [`.env.example`](../.env.example) | API keys and feature flags |
| `<example-package>/services.cloud.yaml` | Example-local cloud (NVCF) service catalog |
| `<example-package>/services.local.yaml` | Example-local on-prem catalog merged automatically when sidecars are reachable |
| `<example-package>/prompts.yaml` | Example-local persona and system prompt presets selectable from the UI |

## How-To Guides

| Guide | Description |
|-------|-------------|
| [Configure Services](./how-to/configure-services.md) | Switch and add LLM, ASR, and TTS services via the UI or YAML catalogs |
| [Configure Prompts](./how-to/configure-prompts.md) | Switch and add prompt presets via the UI or example-local prompt catalogs |
| [Enable Multilingual Voice Agent](./how-to/enable-multilingual.md) | Enable prompt-driven multilingual replies with automatic TTS language switching |
| [Configure TTS Settings](./how-to/configure-tts-settings.md) | Set up TTS voice, cloud endpoints, and text filters |
| [Enable Zero-Shot TTS](./how-to/enable-zero-shot-tts.md) | Clone any voice from a short audio sample using the Magpie Zero-shot model |
| [Tune Pipeline Performance](./how-to/tune-pipeline-performance.md) | Smart turn detection, audio debugging, chat history, and transport options |
| [Enable OpenTelemetry Tracing](./how-to/enable-opentelemetry-tracing.md) | Monitor latency, debug issues, and analyze conversation flows with Phoenix or any OTLP backend |
