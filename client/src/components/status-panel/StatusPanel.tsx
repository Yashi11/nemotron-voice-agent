// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useApp } from "../../context/useApp";
import { PipelineModeSelector } from "../PipelineModeSelector";
import { PipelineExampleSelector } from "../PipelineExampleSelector";
import { TransportSelector } from "../TransportSelector";
import { PromptSelector } from "../PromptSelector";
import { ToolsSection } from "../ToolsSection";
import { VoiceSettings } from "../VoiceSettings";

export function StatusPanel() {
  const { selectedExample } = useApp();
  const isS2S = selectedExample?.family === "speech-to-speech";

  return (
    <aside className="status-panel">
      <PipelineModeSelector />
      <PipelineExampleSelector />
      <TransportSelector />
      <PromptSelector />
      {!isS2S && <ToolsSection />}
      {!isS2S && <VoiceSettings />}
    </aside>
  );
}
