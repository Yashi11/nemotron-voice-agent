// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useConnectionState } from "../hooks/useConnectionState";
import { type TransportType } from "../context/AppContext";
import { useApp } from "../context/useApp";
import { PanelSection } from "./PanelSection";

const TRANSPORTS: { id: TransportType; label: string }[] = [
  { id: "webrtc", label: "WebRTC" },
  { id: "websocket", label: "WebSocket" },
];

export function TransportSelector() {
  const { isLocked } = useConnectionState();
  const { selectedTransport, setTransport } = useApp();

  return (
    <PanelSection label="TRANSPORT">
      <div className="transport-options">
        {TRANSPORTS.map((t) => (
          <button
            key={t.id}
            className={`transport-btn ${selectedTransport === t.id ? "transport-btn--active" : ""}`}
            onClick={() => setTransport(t.id)}
            disabled={isLocked}
            aria-pressed={selectedTransport === t.id}
          >
            {t.label}
          </button>
        ))}
      </div>
    </PanelSection>
  );
}
