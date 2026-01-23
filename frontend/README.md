# Frontend Directory

This directory contains both WebRTC and WebSocket UI implementations for the Nemotron Voice Agent.

## Structure

```
frontend/
├── Dockerfile           # Unified Dockerfile for both UIs
├── webrtc_ui/          # WebRTC UI (React/Vite application)
└── websocket_ui/       # WebSocket UI (Static HTML)
```

## Usage

The UI type is automatically selected based on the `TRANSPORT` environment variable in your `.env` file:

- `TRANSPORT=WEBRTC` (default) - Uses the WebRTC UI
- `TRANSPORT=WEBSOCKET` - Uses the WebSocket UI

## Running UI Service

The unified Dockerfile builds both UIs and serves the appropriate one based on the `TRANSPORT` variable:

```bash
# Run with WebRTC UI (default)
docker-compose up ui-app

# Run with WebSocket UI
TRANSPORT=WEBSOCKET docker-compose up ui-app
```

The UI will be available at `http://localhost:9000`

## Development

### WebRTC UI
The WebRTC UI is a React application built with Vite. For local development:

```bash
cd webrtc_ui
npm install
npm run dev
```

### WebSocket UI
The WebSocket UI consists of static HTML files in the `websocket_ui/static/` directory. You can serve them directly with any HTTP server.
