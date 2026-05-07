// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useState } from "react";
import { usePipecatClient } from "@pipecat-ai/client-react";
import { useConnectionState } from "../hooks/useConnectionState";
import { useApp } from "../context/useApp";
import {
  createSessionConfig,
  createWebRTCSession,
  type DeploymentOption,
  type LLMService,
  type Prompt,
  type SimpleService,
} from "../api";
import { DevicesSection } from "./status-panel/DevicesSection";

type StartBotClient = {
  connect: (args: { wsUrl?: string; webrtcUrl?: string }) => Promise<void>;
  disconnect: () => Promise<void>;
};

const WEBRTC_CONNECT_TIMEOUT_MS = 30_000;
const WEBRTC_TIMEOUT_ERROR_NAME = "WebRTCConnectionTimeoutError";

type SessionConfigOptions = {
  selectedExample: DeploymentOption;
  selectedS2SServer: string;
  selectedLLM?: LLMService;
  selectedASR?: SimpleService;
  selectedTTS?: SimpleService;
  selectedVoiceId: string;
  selectedPrompt?: Prompt;
  selectedPromptKey: string;
};

function getConnectionErrorMessage(err: unknown): string {
  const fallback = "Connection failed. Please try again.";
  const rawMessage =
    err instanceof Error ? err.message :
    typeof err === "string" ? err :
    fallback;

  const jsonStart = rawMessage.indexOf("{");
  if (jsonStart >= 0) {
    try {
      const parsed = JSON.parse(rawMessage.slice(jsonStart)) as { info?: string; detail?: string };
      if (parsed.info) return parsed.info;
      if (parsed.detail) return parsed.detail;
    } catch {
      // Fall back to the original message when the SDK error is not JSON.
    }
  }

  return rawMessage.replace(/^HTTP \d+:?\s*/, "") || fallback;
}

function getWebRTCTimeoutMessage(): string {
  const timeoutSecs = WEBRTC_CONNECT_TIMEOUT_MS / 1000;
  return `WebRTC connection timed out after ${timeoutSecs}s. Check browser microphone permissions and network connectivity, or configure TURN if connecting from another network.`;
}

function isWebRTCTimeoutError(err: unknown): boolean {
  return err instanceof Error && err.name === WEBRTC_TIMEOUT_ERROR_NAME;
}

async function withWebRTCConnectTimeout(promise: Promise<void>): Promise<void> {
  let timeoutId = 0;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = window.setTimeout(() => {
      const error = new Error("WebRTC connection timed out");
      error.name = WEBRTC_TIMEOUT_ERROR_NAME;
      reject(error);
    }, WEBRTC_CONNECT_TIMEOUT_MS);
  });

  try {
    await Promise.race([promise, timeout]);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function applyService(
  config: Record<string, string>,
  enabled: boolean,
  prefix: "asr" | "tts",
  service: SimpleService | undefined,
  optional: Record<string, string | undefined>,
): void {
  if (!enabled || !service) return;
  config[`${prefix}_id`] = service.id;
  if (!service.builtIn) {
    config[`${prefix}_server`] = service.server;
    for (const [field, value] of Object.entries(optional)) {
      if (value) config[`${prefix}_${field}`] = value;
    }
  }
}

function buildSessionConfig({
  selectedExample,
  selectedS2SServer,
  selectedLLM,
  selectedASR,
  selectedTTS,
  selectedVoiceId,
  selectedPrompt,
  selectedPromptKey,
}: SessionConfigOptions): Record<string, string> {
  const slots = new Set(selectedExample.slots);
  const isAgenticAirline = selectedExample.id === "agentic-airline";
  const config: Record<string, string> = { pipeline_mode: selectedExample.key };

  if (slots.has("s2s") && selectedS2SServer) config.s2s_server = selectedS2SServer;

  if (slots.has("llm") && selectedLLM) {
    config.llm_id = selectedLLM.id;
    if (!selectedLLM.builtIn) {
      config.model_id = selectedLLM.modelId;
      config.base_url = selectedLLM.baseUrl;
      if (selectedLLM.systemPrompt) config.system_prompt = selectedLLM.systemPrompt;
      if (selectedLLM.extraParams) config.extra_params = selectedLLM.extraParams;
    }
  }

  applyService(config, slots.has("asr"), "asr", selectedASR, {
    model: selectedASR?.model,
    function_id: selectedASR?.functionId,
  });
  applyService(config, slots.has("tts"), "tts", selectedTTS, {
    function_id: selectedTTS?.functionId,
  });

  const voiceToSend = selectedVoiceId || selectedTTS?.voiceId;
  if (slots.has("tts") && voiceToSend) config.tts_voice_id = voiceToSend;

  if (selectedPromptKey && !isAgenticAirline) {
    config.prompt_key = selectedPromptKey;
    if (selectedPrompt && !selectedPrompt.builtIn) config.prompt_content = selectedPrompt.content;
  }

  return config;
}

export function Header() {
  const client = usePipecatClient() as StartBotClient | undefined;
  const { isConnected, isConnecting } = useConnectionState();
  const { selectedExample, selectedTransport, selectedS2SServer, selectedLLM, selectedASR, selectedTTS, selectedVoiceId, selectedPrompt, selectedPromptKey } = useApp();
  const [connectionError, setConnectionError] = useState("");

  const handleClick = async () => {
    setConnectionError("");

    try {
      if (!client) {
        throw new Error("Connection client is not ready yet.");
      }
      if (!selectedExample) {
        throw new Error("Pipeline example not loaded yet. Please retry in a moment.");
      }

      if (isConnected) {
        await client.disconnect();
      } else {
        const config = buildSessionConfig({
          selectedExample,
          selectedS2SServer,
          selectedLLM,
          selectedASR,
          selectedTTS,
          selectedVoiceId,
          selectedPrompt,
          selectedPromptKey,
        });

        if (selectedTransport === "websocket") {
          const sessionId = await createSessionConfig(config);
          const qs = `session_id=${sessionId}`;
          const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
          await client.connect({ wsUrl: `${wsProto}//${window.location.host}/api/ws?${qs}` });
        } else {
          const webrtcUrl = await createWebRTCSession(config);
          await withWebRTCConnectTimeout(client.connect({ webrtcUrl }));
        }
      }
    } catch (err) {
      if (isWebRTCTimeoutError(err)) {
        await client?.disconnect().catch(() => undefined);
        setConnectionError(getWebRTCTimeoutMessage());
      } else {
        setConnectionError(getConnectionErrorMessage(err));
      }
      console.error("Connection error:", err);
    }
  };

  const buttonText = isConnecting ? "Connecting..." : isConnected ? "Disconnect" : "Connect";

  return (
    <header className="px-4 py-3 border-b">
      <div className="d-flex justify-between items-center">
        <h1 className="text-lg font-semibold">
          <span style={{ color: "#76b900", fontWeight: 700, letterSpacing: "0.08em" }}>Nemotron</span> Voice Agent
        </h1>
        <div className="d-flex items-center gap-3">
          {isConnected && <DevicesSection />}
          <button
            className={isConnected ? "btn-secondary" : "btn-primary"}
            onClick={handleClick}
            disabled={isConnecting}
          >
            {buttonText}
          </button>
        </div>
      </div>
      {connectionError && (
        <p className="mt-2 text-xs" style={{ color: "#f87171" }}>
          {connectionError}
        </p>
      )}
    </header>
  );
}
