// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useEffect, useMemo } from "react";
import { PipecatClient } from "@pipecat-ai/client-js";
import { PipecatClientProvider, PipecatClientAudio } from "@pipecat-ai/client-react";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { WebSocketTransport, ProtobufFrameSerializer, WavMediaManager } from "@pipecat-ai/websocket-transport";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient, useIceServers } from "./api";
import { AppProvider } from "./context/AppContext";
import { useApp } from "./context/useApp";
import { Header } from "./components/Header";
import { StatusPanel } from "./components/status-panel";
import { Sidebar } from "./components/Sidebar";
import { CenterPanel } from "./components/content";
import { webRTCTransportUnavailableMessage } from "./utils";

const EMPTY_ICE_SERVERS: RTCIceServer[] = [];
const WEBSOCKET_RECORDER_SAMPLE_RATE = 16000;
const WEBSOCKET_PLAYER_SAMPLE_RATE = 16000;
const WEBSOCKET_RECORDER_CHUNK_SIZE = 512;

function AppInner() {
  const { selectedTransport, setTransport, webRTCAvailable } = useApp();
  const { data: iceConfig, isFetched: iceServersLoaded } = useIceServers();
  const iceServers = iceConfig?.iceServers ?? EMPTY_ICE_SERVERS;

  const clientState = useMemo<{ client: PipecatClient | null; transportInitError: string }>(() => {
    const createWebSocketClient = () => new PipecatClient({
      transport: new WebSocketTransport({
        mediaManager: new WavMediaManager(WEBSOCKET_RECORDER_CHUNK_SIZE, WEBSOCKET_RECORDER_SAMPLE_RATE),
        serializer: new ProtobufFrameSerializer(),
        recorderSampleRate: WEBSOCKET_RECORDER_SAMPLE_RATE,
        playerSampleRate: WEBSOCKET_PLAYER_SAMPLE_RATE,
      }),
      enableMic: true,
      enableCam: false,
      enableScreenShare: false,
    });

    if (selectedTransport === "websocket") {
      try {
        return { client: createWebSocketClient(), transportInitError: "" };
      } catch (err) {
        const message = err instanceof Error ? err.message : "WebSocket transport initialization failed.";
        return { client: null, transportInitError: message };
      }
    }
    if (!webRTCAvailable) return { client: null, transportInitError: webRTCTransportUnavailableMessage() };
    if (!iceServersLoaded) return { client: null, transportInitError: "" };
    try {
      return {
        client: new PipecatClient({
          transport: new SmallWebRTCTransport({ iceServers }),
          enableMic: true,
        }),
        transportInitError: "",
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : webRTCTransportUnavailableMessage();
      console.warn("WebRTC transport initialization failed; switching to WebSocket transport:", err);
      return { client: null, transportInitError: message };
    }
  }, [iceServers, iceServersLoaded, selectedTransport, webRTCAvailable]);

  useEffect(() => {
    if (selectedTransport === "webrtc" && clientState.transportInitError) {
      setTransport("websocket");
    }
  }, [clientState.transportInitError, selectedTransport, setTransport]);

  const client = clientState.client;

  if (selectedTransport === "webrtc") {
    if (!webRTCAvailable) {
      return (
        <div className="h-screen d-flex items-center justify-center px-4 text-center">
          <div>
            <h2 className="text-lg font-semibold mb-2">Voice transport unavailable</h2>
            <p className="text-secondary">{webRTCTransportUnavailableMessage()}</p>
          </div>
        </div>
      );
    }

    if (clientState.transportInitError) {
      return (
        <div className="h-screen d-flex items-center justify-center px-4 text-center">
          <div>
            <h2 className="text-lg font-semibold mb-2">Switching transport</h2>
            <p className="text-secondary">
              WebRTC is unavailable in this browser session ({clientState.transportInitError}). Switching to WebSocket.
            </p>
          </div>
        </div>
      );
    }
  }

  if (!client) {
    return <div className="h-screen d-flex items-center justify-center">Loading connection...</div>;
  }

  return (
    <PipecatClientProvider client={client}>
      <div className="h-screen d-flex flex-col overflow-hidden">
        <Header />
        <div className="flex-1 d-flex overflow-hidden">
          <StatusPanel />
          <CenterPanel />
          <Sidebar />
        </div>
        <PipecatClientAudio />
      </div>
    </PipecatClientProvider>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppProvider>
        <AppInner />
      </AppProvider>
    </QueryClientProvider>
  );
}

export default App;
