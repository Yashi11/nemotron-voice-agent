// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useConnectionState } from "../hooks/useConnectionState";
import { useApp } from "../context/useApp";
import { PanelSection } from "./PanelSection";

function renderOptions(items: Array<{ id: string; name: string }>) {
  return items.map((svc) => (
    <option key={svc.id} value={svc.id}>
      {svc.name}
    </option>
  ));
}

export function ModelSelector() {
  const { isLocked } = useConnectionState();
  const { llms, selectedLLMId, selectLLM } = useApp();
  const selfHosted = llms.filter((svc) => svc.builtIn && svc.source === "self-hosted");
  const cloud = llms.filter((svc) => svc.builtIn && svc.source === "cloud-nim");
  const custom = llms.filter((svc) => !svc.builtIn);

  return (
    <PanelSection label="LLM MODEL">
      <select
        className="select-dark select-full"
        value={selectedLLMId}
        onChange={(e) => selectLLM(e.target.value)}
        disabled={isLocked}
      >
        {selfHosted.length > 0 && <optgroup label="Self-hosted">{renderOptions(selfHosted)}</optgroup>}
        {cloud.length > 0 && <optgroup label="NVIDIA Cloud">{renderOptions(cloud)}</optgroup>}
        {custom.length > 0 && <optgroup label="Custom">{renderOptions(custom)}</optgroup>}
      </select>
    </PanelSection>
  );
}
