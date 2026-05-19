// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useConnectionState } from "../hooks/useConnectionState";
import { useApp } from "../context/useApp";

export function PipelineModeSelector() {
  const { isLocked } = useConnectionState();
  const { selectedExample, selectExample, deploymentOptions, availablePipelines, deploymentSelectable } = useApp();
  const disabled = isLocked || !deploymentSelectable;

  // First option per family becomes the family default — clicking the family
  // selector lands on it.
  const familyDefaults = new Map<string, string>();
  for (const option of deploymentOptions) {
    if (!familyDefaults.has(option.family)) familyDefaults.set(option.family, option.key);
  }
  const pipelines = availablePipelines.filter((pipeline) => familyDefaults.has(pipeline.id));

  if (pipelines.length <= 1) return null;

  return (
    <div className="panel-section">
      <p className="panel-label">PIPELINE</p>
      <div className="transport-options">
        {pipelines.map((pipeline) => (
          <button
            key={pipeline.id}
            className={`transport-btn ${selectedExample?.family === pipeline.id ? "transport-btn--active" : ""}`}
            onClick={() => selectExample(familyDefaults.get(pipeline.id)!)}
            disabled={disabled}
          >
            {pipeline.label}
          </button>
        ))}
      </div>
    </div>
  );
}
