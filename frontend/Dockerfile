# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD 2-Clause License

# Build stage for WebRTC UI
FROM node:18-alpine AS builder

# Image metadata
LABEL stage="builder"
LABEL description="UI build environment"

# Set working directory
WORKDIR /app

# Copy webrtc_ui package files and install dependencies
COPY webrtc_ui/package*.json ./
RUN npm ci --frozen-lockfile \
    && npm cache clean --force

# Copy webrtc_ui source code and build
COPY webrtc_ui/ .
RUN npm run build \
    && rm -rf node_modules

# Production stage
FROM python:3.12-alpine AS production

# Image metadata
LABEL maintainer="NVIDIA"
LABEL description="Voice Agent UI static server"
LABEL version="1.0"

# Set working directory
WORKDIR /app

# Copy both UI static files
COPY --from=builder /app/dist ./webrtc_static
COPY websocket_ui/static ./websocket_static

# Port configuration
EXPOSE 8000

# Start command, by default serving the WebRTC UI
CMD ["python", "-m", "http.server", "8000", "--directory", "webrtc_static"]