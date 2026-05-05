// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { VoiceVisualizer } from "@pipecat-ai/client-react";
import { useConnectionState } from "../hooks/useConnectionState";
import { StatusSection } from "./status-panel/StatusSection";
import { SessionSection } from "./status-panel/SessionSection";

const VISUALIZER_PROPS = {
  backgroundColor: "#0a0a0a",
  barColor: "#76b900",
  barCount: 20,
  barGap: 4,
  barWidth: 8,
  barMaxHeight: 60,
  barLineCap: "round" as const,
};

export function Sidebar() {
  const { isConnected } = useConnectionState();

  return (
    <aside className="d-flex flex-col gap-4 p-4" style={{ width: "300px" }}>
      <StatusSection />
      <SessionSection />

      {isConnected && (
        <>
          <div className="card p-3">
            <p className="text-xs text-secondary mb-2">USER AUDIO</p>
            <VoiceVisualizer participantType="local" {...VISUALIZER_PROPS} />
          </div>

          <div className="card p-3">
            <p className="text-xs text-secondary mb-2">BOT AUDIO</p>
            <VoiceVisualizer participantType="bot" {...VISUALIZER_PROPS} />
          </div>
        </>
      )}
    </aside>
  );
}
