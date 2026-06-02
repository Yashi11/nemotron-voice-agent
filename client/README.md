# Nemotron Voice Agent Client

React/TypeScript web client for the Nemotron Voice Agent, built with [Vite](https://vite.dev/) and the [Pipecat Client SDK](https://docs.pipecat.ai/client/introduction).

## Features

- **Dual pipeline modes**: Cascaded (ASR → LLM → TTS) and Speech-to-Speech
- **Dual transport**: WebRTC (recommended) and WebSocket
- **Runtime service switching**: Add/remove LLM, ASR, TTS services without redeployment
- **Prompt management**: Select built-in personas or create custom system prompts
- **Voice selection**: Browse and preview TTS voices with language filtering
- **Audio visualizers**: Real-time input/output waveform display
- **Metrics dashboard**: TTFB latency charts, token usage, and connection status
- **Conversation transcript**: Live ASR and bot response display

## Development

```bash
npm install
npm run dev
```

The dev server runs at `http://localhost:5173` and proxies API requests to the backend at `https://localhost:7860`.

## Production Build

```bash
npm run build
```

Output goes to `dist/`, which the Python server serves automatically.

## Linting

```bash
npm run lint
```
