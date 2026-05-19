// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useConnectionState } from "../hooks/useConnectionState";
import { useApp } from "../context/useApp";

export function PipelineExampleSelector() {
  const { isLocked } = useConnectionState();
  const { selectedExample, selectExample, deploymentOptions, deploymentSelectable } = useApp();
  const disabled = isLocked || !deploymentSelectable;

  if (!selectedExample) return null;

  const examplesInFamily = deploymentOptions.filter((option) => option.family === selectedExample.family);

  return (
    <div className="panel-section">
      <p className="panel-label">PIPELINE EXAMPLE</p>
      <select
        className="select-dark select-full"
        value={selectedExample.key}
        onChange={(e) => selectExample(e.target.value)}
        disabled={disabled}
        aria-label="Pipeline example"
      >
        {examplesInFamily.map((option) => (
          <option key={option.key} value={option.key}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
