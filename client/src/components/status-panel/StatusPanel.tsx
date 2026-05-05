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
  const { pipelineMode, cascadedSubMode, setSelectedS2SServer } = useApp();

  const isAgenticAirline = pipelineMode === "cascaded" && cascadedSubMode === "agentic_airline";

  return (
    <aside className="status-panel">
      <PipelineModeSelector />
      <PipelineExampleSelector />
      <TransportSelector />
      {!isAgenticAirline && <PromptSelector />}
      {pipelineMode === "s2s" ? (
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
