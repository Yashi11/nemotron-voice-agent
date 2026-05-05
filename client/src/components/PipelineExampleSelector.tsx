// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { type CascadedSubMode } from "../context/AppContext";
import { useConnectionState } from "../hooks/useConnectionState";
import { useApp } from "../context/useApp";

const CASCADED_SUB_MODES: { id: CascadedSubMode; label: string }[] = [
  { id: "simple", label: "Generic Cascaded" },
  { id: "agentic_airline", label: "Agentic Airline" },
];

export function PipelineExampleSelector() {
  const { isLocked } = useConnectionState();
  const { pipelineMode, cascadedSubMode, setCascadedSubMode, agenticAirlineAvailable, deploymentSelectable } = useApp();
  const modes = agenticAirlineAvailable
    ? CASCADED_SUB_MODES
    : CASCADED_SUB_MODES.filter((mode) => mode.id !== "agentic_airline");
  const disabled = isLocked || !deploymentSelectable;

  if (pipelineMode !== "cascaded") return null;

  return (
    <div className="panel-section">
      <p className="panel-label">PIPELINE EXAMPLE</p>
      <select
        className="select-dark select-full"
        value={cascadedSubMode}
        onChange={(e) => setCascadedSubMode(e.target.value as CascadedSubMode)}
        disabled={disabled}
        aria-label="Cascaded pipeline example"
      >
        {modes.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}
          </option>
        ))}
      </select>
    </div>
  );
}
