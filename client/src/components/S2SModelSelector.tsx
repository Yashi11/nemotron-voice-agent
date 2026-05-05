// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useEffect, useMemo, useRef, useState } from "react";
import { useServiceCatalog } from "../api";
import { useConnectionState } from "../hooks/useConnectionState";

export function S2SModelSelector({ onSelect }: { onSelect?: (server: string) => void }) {
  const { data: catalog, isLoading } = useServiceCatalog();
  const { isLocked } = useConnectionState();
  const [selected, setSelected] = useState("");
  const notifiedRef = useRef(false);

  const models = useMemo(() => catalog?.s2s ?? [], [catalog]);
  const effectiveSelected = selected || models[0]?.id || "";

  useEffect(() => {
    if (effectiveSelected && !notifiedRef.current && onSelect) {
      notifiedRef.current = true;
      const model = models.find((m) => m.id === effectiveSelected);
      onSelect(model?.server ? String(model.server) : "");
    }
  }, [effectiveSelected, models, onSelect]);

  const handleChange = (id: string) => {
    setSelected(id);
    const model = models.find((m) => m.id === id);
    if (model && onSelect) {
      onSelect(model.server ? String(model.server) : "");
    }
  };

  if (isLoading) {
    return (
      <div className="panel-section">
        <p className="panel-label">S2S MODEL</p>
        <p style={{ fontSize: "11px", color: "var(--text-muted)" }}>Loading...</p>
      </div>
    );
  }

  if (models.length === 0) return null;

  return (
    <div className="panel-section">
      <p className="panel-label">S2S MODEL</p>
      <select
        className="select-dark select-full"
        value={effectiveSelected}
        onChange={(e) => handleChange(e.target.value)}
        disabled={isLocked}
        aria-label="Speech-to-speech model"
      >
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </select>
    </div>
  );
}
