// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useEffect } from "react";
import { useConnectionState } from "../hooks/useConnectionState";
import { useApp } from "../context/useApp";
import { PanelSection } from "./PanelSection";

const MULTILINGUAL_PROMPT_KEY = "multilingual_voice_assistant";

export function PromptSelector() {
  const { isLocked } = useConnectionState();
  const { prompts, promptsLoading, selectedPromptKey, selectPrompt, selectedPrompt, selectedASR, selectedTTS } = useApp();
  const multilingualReady = selectedASR?.id.endsWith(":parakeet-rnnt") && selectedTTS?.id.endsWith(":magpie-tts");
  const visiblePrompts = multilingualReady ? prompts : prompts.filter((p) => p.key !== MULTILINGUAL_PROMPT_KEY);

  useEffect(() => {
    if (selectedPromptKey === MULTILINGUAL_PROMPT_KEY && !multilingualReady) {
      const fallback = prompts.find((p) => p.key !== MULTILINGUAL_PROMPT_KEY);
      if (fallback) selectPrompt(fallback.key);
    }
  }, [multilingualReady, prompts, selectPrompt, selectedPromptKey]);

  if (promptsLoading) {
    return <PanelSection label="PROMPT" loading loadingText="Loading..." />;
  }

  if (prompts.length === 0) return null;

  return (
    <PanelSection label="PROMPT">
      <select
        className="select-dark select-full"
        value={selectedPromptKey}
        onChange={(e) => {
          if (e.target.value === MULTILINGUAL_PROMPT_KEY && !multilingualReady) return;
          selectPrompt(e.target.value);
        }}
        title={selectedPrompt?.description || selectedPrompt?.content || ""}
        disabled={isLocked}
      >
        {visiblePrompts.map((p) => (
          <option key={p.key} value={p.key} title={p.description || p.content}>
            {p.key}
          </option>
        ))}
      </select>
    </PanelSection>
  );
}
