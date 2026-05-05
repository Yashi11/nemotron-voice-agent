// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useState, useMemo, useCallback } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { usePipecatClient, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { useTTSConfig } from "../api";
import { useConnectionState } from "../hooks/useConnectionState";
import { useApp } from "../context/useApp";
import { PanelSection } from "./PanelSection";

type LanguageSwitchedMessage = {
  type?: string;
  language?: string;
  voice_id?: string;
};

type VoiceOverrideState = {
  serviceId: string;
  language: string;
  voiceId: string;
};

export function VoiceSettings() {
  const client = usePipecatClient();
  const { isConnected } = useConnectionState();
  const { selectedTTS, setSelectedVoiceId } = useApp();

  const selectedTTSServer = selectedTTS?.server;

  const { data: ttsConfig, isLoading } = useTTSConfig(selectedTTSServer, selectedTTS?.voiceId);
  const [voiceOverride, setVoiceOverride] = useState<VoiceOverrideState>({
    serviceId: "",
    language: "",
    voiceId: "",
  });

  useRTVIClientEvent(
    RTVIEvent.ServerMessage,
    useCallback((message: LanguageSwitchedMessage) => {
      if (message?.type === "language-switched") {
        const lang = message.language ?? "";
        const voiceId = message.voice_id ?? "";
        if (lang || voiceId) {
          setVoiceOverride({
            serviceId: selectedTTS?.id ?? "",
            language: lang,
            voiceId,
          });
        }
      }
    }, [selectedTTS?.id])
  );

  const defaultVoice = useMemo(() => {
    if (!ttsConfig?.voices?.length) return null;
    const selectedServiceVoice = selectedTTS?.voiceId || "";
    if (selectedServiceVoice) {
      const match = ttsConfig.voices.find((voice) => voice.id === selectedServiceVoice);
      if (match) return match;
    }
    if (ttsConfig.defaultVoiceId) {
      const match = ttsConfig.voices.find((voice) => voice.id === ttsConfig.defaultVoiceId);
      if (match) return match;
    }
    const enVoice = ttsConfig.voices.find((voice) => voice.language.toUpperCase() === "EN-US");
    return enVoice || ttsConfig.voices[0];
  }, [ttsConfig, selectedTTS?.voiceId]);

  const hasActiveOverride = voiceOverride.serviceId === (selectedTTS?.id ?? "");
  const activeLang = (hasActiveOverride ? voiceOverride.language : "") || (defaultVoice?.language.replace("_", "-") ?? "");
  const activeVoice = (hasActiveOverride ? voiceOverride.voiceId : "") || defaultVoice?.id || "";

  const languages = ttsConfig?.languages ?? [];

  const filteredVoices = useMemo(() => {
    if (!ttsConfig || !activeLang) return [];
    const langUpper = activeLang.toUpperCase();
    return ttsConfig.voices.filter((v) => v.language.toUpperCase() === langUpper);
  }, [ttsConfig, activeLang]);

  const handleLangChange = (lang: string) => {
    setVoiceOverride({
      serviceId: selectedTTS?.id ?? "",
      language: lang,
      voiceId: "",
    });
    setSelectedVoiceId("");
  };

  const handleVoiceChange = (voiceId: string) => {
    setVoiceOverride((current) => ({
      serviceId: selectedTTS?.id ?? "",
      language: current.serviceId === (selectedTTS?.id ?? "") ? current.language : activeLang,
      voiceId,
    }));
    setSelectedVoiceId(voiceId);
    if (isConnected && client && voiceId) {
      client.sendClientMessage("set-voice", {
        voice_id: voiceId,
        language: activeLang,
      });
    }
  };

  if (isLoading) {
    return <PanelSection label="VOICE SETTINGS" loading loadingText="Loading..." />;
  }

  if (!ttsConfig || ttsConfig.voices.length === 0) {
    return (
      <PanelSection label="VOICE SETTINGS">
        <p style={{ fontSize: "11px", color: "var(--text-muted)" }}>No voices available for this TTS server</p>
      </PanelSection>
    );
  }

  return (
    <PanelSection label="VOICE SETTINGS">
      <div className="settings-row">
        <span className="settings-label">Language</span>
        <select
          className="select-dark"
          value={activeLang}
          onChange={(e) => handleLangChange(e.target.value)}
          disabled
          title="Language selection is not yet supported"
        >
          {languages.map((lang) => (
            <option key={lang} value={lang}>{lang}</option>
          ))}
        </select>
      </div>

      <div className="settings-row">
        <span className="settings-label">Voice</span>
        <select
          className="select-dark"
          value={activeVoice}
          onChange={(e) => handleVoiceChange(e.target.value)}
        >
          <option value="">Select voice</option>
          {filteredVoices.map((v) => (
            <option key={v.id} value={v.id}>{v.name}</option>
          ))}
        </select>
      </div>
    </PanelSection>
  );
}
