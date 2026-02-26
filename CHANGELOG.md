## Changelog
All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-03-03

Nemotron Voice Agent is a comprehensive, end-to-end voice agent blueprint built with NVIDIA Nemotron ASR, LLM, and TTS for acceleration and scaling. This is the first release of the Nemotron Voice Agent.

### Added

- End-to-end voice agent pipeline integrating Nemotron ASR, LLM, and TTS with streaming and interruptible conversations
- Pipeline built on open source [Pipecat-ai](https://github.com/pipecat-ai/pipecat) and [nvidia-pipecat](https://github.com/NVIDIA/voice-agent-examples) frameworks
- Support for NVIDIA Nemotron Speech models: Parakeet CTC 1.1B ASR, Parakeet 1.1B RNNT Multilingual ASR, and Magpie TTS Multilingual
- Support for NVIDIA Nemotron LLMs: Nemotron 3 Nano 30B A3B and Llama 3.3 Nemotron Super 49B v1.5 via NVIDIA NIM
- WebRTC transport for low-latency real-time voice communication with custom frontend UI
- Docker Compose-based deployment with optional TURN server for remote access
- Getting Started guide with prerequisites, GPU setup, and step-by-step deployment instructions
- Multilingual Voice Agent support with automatic language detection and seamless language switching during conversations
- Detailed customization options available: configure ASR/LLM/TTS models, adjust pipeline components (speculative speech, buffering, history limits), tune performance and latency, and customize prompts via `.env` and configuration files
- OpenTelemetry support for distributed tracing and monitoring of the complete conversational pipeline
- Jetson Thor deployment guide for edge deployment
- Best practices documentation for production deployment, latency optimization, and UX design
- AI agent deployment skill for Cursor and Claude to assist with deployment on workstation and Jetson Thor
