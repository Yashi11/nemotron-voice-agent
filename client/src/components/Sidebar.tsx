// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useApp } from "../context/useApp";
import { useConnectionState } from "../hooks/useConnectionState";
import { StatusSection } from "./status-panel/StatusSection";
import { SessionSection } from "./status-panel/SessionSection";
import { VoiceLevelVisualizer } from "./VoiceLevelVisualizer";
import { WebcamVisionPanel } from "./WebcamVisionPanel";

const VISUALIZER_PROPS = {
  backgroundColor: "#0a0a0a",
  barColor: "#76b900",
  barCount: 20,
  barGap: 4,
  barWidth: 8,
  barMaxHeight: 44,
  barLineCap: "round" as const,
};

export function Sidebar() {
  const { isConnected } = useConnectionState();
  const { currentSessionId, selectedExample } = useApp();
  const canUseWebcam = selectedExample?.capabilities?.includes("webcam") ?? false;

  return (
    <aside className="sidebar-panel d-flex flex-col" style={{ width: "300px" }}>
      <StatusSection />
      <SessionSection />

      {isConnected && (
        <>
          <div className="card sidebar-card sidebar-audio-card">
            <p className="text-xs text-secondary mb-2">BOT AUDIO</p>
            <div className="sidebar-voice-visualizer">
              <VoiceLevelVisualizer participantType="bot" ariaLabel="Bot audio level" {...VISUALIZER_PROPS} />
            </div>
          </div>

          <div className="card sidebar-card sidebar-audio-card">
            <p className="text-xs text-secondary mb-2">USER AUDIO</p>
            <div className="sidebar-voice-visualizer">
              <VoiceLevelVisualizer participantType="local" ariaLabel="User audio level" {...VISUALIZER_PROPS} />
            </div>
          </div>

          {canUseWebcam && currentSessionId && (
            <div className="card sidebar-card sidebar-webcam-card">
              <p className="text-xs text-secondary mb-2">WEBCAM VISION</p>
              <WebcamVisionPanel sessionId={currentSessionId} />
            </div>
          )}
        </>
      )}
    </aside>
  );
}
