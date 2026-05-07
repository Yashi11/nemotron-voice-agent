// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useConnectionState } from "../hooks/useConnectionState";
import { useApp } from "../context/useApp";

const FAMILY_LABELS: Record<string, string> = {
  cascaded: "Cascaded",
  "speech-to-speech": "Speech-to-Speech",
};

export function PipelineModeSelector() {
  const { isLocked } = useConnectionState();
  const { selectedExample, selectExample, deploymentOptions, deploymentSelectable } = useApp();
  const disabled = isLocked || !deploymentSelectable;

  // First option per family becomes the family default — clicking the family
  // selector lands on it.
  const familyDefaults = new Map<string, string>();
  for (const option of deploymentOptions) {
    if (!familyDefaults.has(option.family)) familyDefaults.set(option.family, option.key);
  }
  const families = Array.from(familyDefaults.keys());

  if (families.length <= 1) return null;

  return (
    <div className="panel-section">
      <p className="panel-label">PIPELINE</p>
      <div className="transport-options">
        {families.map((family) => (
          <button
            key={family}
            className={`transport-btn ${selectedExample?.family === family ? "transport-btn--active" : ""}`}
            onClick={() => selectExample(familyDefaults.get(family)!)}
            disabled={disabled}
          >
            {FAMILY_LABELS[family] ?? family}
          </button>
        ))}
      </div>
    </div>
  );
}
