# Configuration Guide

This is the index of everything you can configure in the Nemotron Voice Agent. Configuration lives in a small set of example-local files plus root `.env` settings, and the sections below index each area. For how the catalog files (`services.cloud.yaml` / `services.local.yaml`) work, see [Configure Services](how-to/configure-services.md).

## Model Service

What ASR / LLM / TTS models are available, their VRAM, precision, and known issues:

| Reference | Covers |
|-----------|--------|
| [Configure LLM](how-to/configure-llm.md) | Nemotron LLM models, reasoning on/off, GPU sizing & precision |
| [Configure ASR](how-to/configure-asr.md) | ASR models, VRAM, hardware support, Domain Adaptation & endpointing |
| [Configure TTS](how-to/configure-tts.md) | TTS models, VRAM, hardware support, voice selection, pronunciation (IPA), and text filters |

## Configuration how-to guides

| Guide | Description |
|-------|-------------|
| [Configure Services](how-to/configure-services.md) | How the catalog works: switch, add, and override LLM/ASR/TTS services via the UI or YAML |
| [Configure Prompts](how-to/configure-prompts.md) | Switch and add prompt presets via the UI or example-local prompt catalogs |
| [Multilingual Voice Agent](../src/examples/multilingual/README.md) | Prompt-driven multilingual replies with automatic TTS language switching (documented in the example) |
| [Enable OpenTelemetry Tracing](how-to/enable-opentelemetry-tracing.md) | Monitor latency and conversation flows with Phoenix or any OTLP backend |
| [Enable a TURN Server](how-to/enable-turn-server.md) | TURN server for remote / cross-network WebRTC access |
| [Enable the Audio Recorder](how-to/enable-audio-recorder.md) | Capture raw ASR/TTS audio per turn for debugging |

## Performance tuning

Pipeline tuning knobs (smart turn, chat-history window, audio buffering, transport) live in [Tune Pipeline Performance](how-to/tune-pipeline-performance.md). For benchmark results, see [Evaluation and Performance](04-evaluation-and-performance.md).
