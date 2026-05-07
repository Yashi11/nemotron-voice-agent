// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useApp } from "../../context/useApp";
import { PipelineModeSelector } from "../PipelineModeSelector";
import { PipelineExampleSelector } from "../PipelineExampleSelector";
import { TransportSelector } from "../TransportSelector";
import { ModelSelector } from "../ModelSelector";
import { S2SModelSelector } from "../S2SModelSelector";
import { PromptSelector } from "../PromptSelector";
import { VoiceSettings } from "../VoiceSettings";

export function StatusPanel() {
  const { selectedExample, setSelectedS2SServer } = useApp();
  const isAgenticAirline = selectedExample?.id === "agentic-airline";
  const isS2S = selectedExample?.family === "speech-to-speech";

  return (
    <aside className="status-panel">
      <PipelineModeSelector />
      <PipelineExampleSelector />
      <TransportSelector />
      {!isAgenticAirline && <PromptSelector />}
      {isS2S ? (
        <S2SModelSelector onSelect={setSelectedS2SServer} />
      ) : (
        <>
          <ModelSelector />
          <VoiceSettings />
        </>
      )}
    </aside>
  );
}
