// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { type PipelineMode } from "../context/AppContext";
import { useConnectionState } from "../hooks/useConnectionState";
import { useApp } from "../context/useApp";

const MODES: { id: PipelineMode; label: string }[] = [
  { id: "cascaded", label: "Cascaded" },
  { id: "s2s", label: "Speech-to-Speech" },
];

export function PipelineModeSelector() {
  const { isLocked } = useConnectionState();
  const { pipelineMode, setPipelineMode, deploymentSelectable } = useApp();
  const disabled = isLocked || !deploymentSelectable;

  return (
    <div className="panel-section">
      <p className="panel-label">PIPELINE</p>
      <div className="transport-options">
        {MODES.map((m) => (
          <button
            key={m.id}
            className={`transport-btn ${pipelineMode === m.id ? "transport-btn--active" : ""}`}
            onClick={() => setPipelineMode(m.id)}
            disabled={disabled}
          >
            {m.label}
          </button>
        ))}
      </div>
    </div>
  );
}
