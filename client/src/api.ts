// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useQuery, QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: Infinity, retry: 1 } },
});

export type BuiltInServiceSource = "cloud-nim" | "self-hosted";

export interface LLMService {
  id: string;
  name: string;
  modelId: string;
  baseUrl: string;
  systemPrompt: string;
  extraParams: string;
  builtIn: boolean;
  source?: BuiltInServiceSource;
}

export interface Prompt {
  key: string;
  description: string;
  content: string;
  builtIn: boolean;
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 200)}` : ""}`);
  }
  return res.json();
}

function normalizeServiceSource(source: unknown): BuiltInServiceSource | undefined {
  return source === "cloud-nim" || source === "self-hosted" ? source : undefined;
}

const serviceCatalogQueryOptions = {
  queryKey: ["services"] as const,
  queryFn: () => fetchJson<ServiceCatalog>("/api/services"),
};

export function useDefaultLLMs() {
  return useQuery({
    ...serviceCatalogQueryOptions,
    select: (catalog): LLMService[] =>
      (catalog.llm ?? []).map((e) => ({
        id: e.id,
        name: e.name,
        modelId: String(e.model_id ?? ""),
        baseUrl: String(e.base_url ?? ""),
        systemPrompt: String(e.system_prompt ?? ""),
        extraParams: String(e.extra_params ?? ""),
        builtIn: true,
        source: normalizeServiceSource(e.source),
      })),
  });
}

export function useDefaultPrompts() {
  return useQuery<Prompt[]>({
    queryKey: ["prompts"],
    queryFn: () => fetchJson<Prompt[]>("/api/prompts"),
    select: (data) => data.map((p) => ({ ...p, builtIn: true })),
  });
}

export interface SimpleService {
  id: string;
  name: string;
  server: string;
  model?: string;
  voiceId?: string;
  functionId?: string;
  builtIn: boolean;
  source?: BuiltInServiceSource;
}

export function useDefaultASR() {
  return useQuery({
    ...serviceCatalogQueryOptions,
    select: (catalog): SimpleService[] =>
      (catalog.asr ?? []).map((e) => ({
        id: e.id,
        name: e.name,
        server: String(e.server ?? ""),
        model: e.model ? String(e.model) : undefined,
        functionId: e.function_id ? String(e.function_id) : undefined,
        builtIn: true,
        source: normalizeServiceSource(e.source),
      })),
  });
}

export function useDefaultTTS() {
  return useQuery({
    ...serviceCatalogQueryOptions,
    select: (catalog): SimpleService[] =>
      (catalog.tts ?? []).map((e) => ({
        id: e.id,
        name: e.name,
        server: String(e.server ?? ""),
        voiceId: e.voice_id ? String(e.voice_id) : undefined,
        functionId: e.function_id ? String(e.function_id) : undefined,
        builtIn: true,
        source: normalizeServiceSource(e.source),
      })),
  });
}

export interface TTSVoice {
  id: string;
  name: string;
  language: string;
}

export interface TTSConfig {
  languages: string[];
  voices: TTSVoice[];
  defaultVoiceId: string;
}

export interface ServiceEntry {
  id: string;
  name: string;
  builtIn: boolean;
  source?: BuiltInServiceSource;
  [key: string]: unknown;
}

export interface ServiceCatalog {
  llm: ServiceEntry[];
  tts: ServiceEntry[];
  asr: ServiceEntry[];
  s2s: ServiceEntry[];
}

export interface DeploymentOption {
  family: string;
  id: string;
  key: string;
  label: string;
  slots: string[];
}

export interface DeploymentResponse {
  active: DeploymentOption;
  selectable: boolean;
  options: DeploymentOption[];
}

export interface IceServersResponse {
  iceServers?: RTCIceServer[];
}

export interface IceConfig {
  iceServers: RTCIceServer[];
  hasTurnServer: boolean;
}

function iceServerHasTurn(server: RTCIceServer): boolean {
  const urls = Array.isArray(server.urls) ? server.urls : [server.urls];
  return urls.some((url) => typeof url === "string" && url.trim().toLowerCase().startsWith("turn"));
}

export function useDeployment() {
  return useQuery<DeploymentResponse>({
    queryKey: ["deployment"],
    queryFn: () => fetchJson<DeploymentResponse>("/api/deployment"),
  });
}

export function useIceServers() {
  return useQuery<IceConfig>({
    queryKey: ["ice-servers"],
    queryFn: async () => {
      try {
        const data = await fetchJson<IceServersResponse>("/api/ice-servers");
        const iceServers = data.iceServers ?? [];
        return {
          iceServers,
          hasTurnServer: iceServers.some(iceServerHasTurn),
        };
      } catch {
        return { iceServers: [], hasTurnServer: false };
      }
    },
    retry: false,
  });
}

export function useServiceCatalog() {
  return useQuery(serviceCatalogQueryOptions);
}

export function useTTSConfig(server?: string, voiceId?: string) {
  return useQuery<TTSConfig>({
    queryKey: ["tts-config", server || "default", voiceId || ""],
    queryFn: () => {
      const params = new URLSearchParams();
      if (server) params.set("server", server);
      if (voiceId) params.set("voice_id", voiceId);
      const url = params.size > 0 ? `/api/tts-config?${params.toString()}` : "/api/tts-config";
      return fetchJson<TTSConfig>(url);
    },
  });
}

export async function createSessionConfig(config: Record<string, string>): Promise<string> {
  const res = await fetch("/api/session-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 200)}` : ""}`);
  }
  const data = await res.json();
  return data.session_id;
}

export async function createWebRTCSession(config: Record<string, string>): Promise<string> {
  const res = await fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 200)}` : ""}`);
  }

  const data = await res.json() as { webrtcUrl?: string };
  if (!data.webrtcUrl) {
    throw new Error("WebRTC start did not return a connection URL");
  }
  return data.webrtcUrl;
}
