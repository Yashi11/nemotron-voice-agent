// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { usePipecatClient } from "@pipecat-ai/client-react";
import { useApp } from "../../context/useApp";
import { StatusRow } from "./StatusRow";

const TRANSPORT_LABELS: Record<string, string> = {
  webrtc: "WebRTC",
  websocket: "WebSocket",
};

export function SessionSection() {
  const client = usePipecatClient();
  const { selectedTransport } = useApp();

  return (
    <div className="panel-section">
      <p className="panel-label">SESSION</p>
      <StatusRow label="Transport" value={TRANSPORT_LABELS[selectedTransport] ?? selectedTransport} />
      <StatusRow label="RTVI" value={client?.version ?? "---"} />
    </div>
  );
}
