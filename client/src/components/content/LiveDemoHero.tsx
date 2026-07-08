// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useCallback, useMemo, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";
import { useApp } from "../../context/useApp";
import { useConnectionState } from "../../hooks/useConnectionState";
import { isRecord } from "../../utils";

type LatencySample = {
  id: string;
  valueMs: number;
  first: boolean;
  timestamp: string;
};

const WAVE_BARS = Array.from({ length: 24 }, (_, index) => index);

function readLatencySample(message: unknown): Omit<LatencySample, "id" | "timestamp"> | null {
  if (!isRecord(message) || message.type !== "user-bot-latency") return null;
  const latency = message.latency;
  if (typeof latency !== "number" || !Number.isFinite(latency)) return null;
  return {
    valueMs: latency < 20 ? latency * 1000 : latency,
    first: message.first === true,
  };
}

function formatLatency(valueMs?: number) {
  if (valueMs === undefined) return "--";
  return `${Math.round(valueMs)} ms`;
}

function median(values: number[]) {
  if (values.length === 0) return undefined;
  const sorted = [...values].sort((a, b) => a - b);
  const midpoint = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[midpoint];
  return (sorted[midpoint - 1] + sorted[midpoint]) / 2;
}

function compactPipelineLabel(label: string) {
  return label
    .replace(/\s+Assistant$/i, "")
    .replace(/\s+Agent$/i, "")
    .replace("Frontend/Backend", "Front/Back");
}

export function LiveDemoHero() {
  const { selectedExample, selectedTransport } = useApp();
  const { isConnected, isConnecting } = useConnectionState();
  const [samples, setSamples] = useState<LatencySample[]>([]);

  useRTVIClientEvent(
    RTVIEvent.ServerMessage,
    useCallback((message: unknown) => {
      const sample = readLatencySample(message);
      if (!sample) return;
      setSamples((prev) => [
        ...prev,
        {
          ...sample,
          id: `${Date.now()}-${prev.length}`,
          timestamp: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          }),
        },
      ].slice(-20));
    }, []),
  );

  const turnSamples = useMemo(() => samples.filter((sample) => !sample.first), [samples]);
  const firstAudioSamples = useMemo(() => samples.filter((sample) => sample.first), [samples]);
  const latestTurnLatency = turnSamples.at(-1)?.valueMs;
  const latestFirstAudioLatency = firstAudioSamples.at(-1)?.valueMs;
  const medianTurnLatency = useMemo(
    () => median(turnSamples.map((sample) => sample.valueMs)),
    [turnSamples],
  );
  const displayLatency = latestTurnLatency ?? latestFirstAudioLatency;
  const latencyLabel = latestTurnLatency !== undefined ? "turn latency" : "first audio";
  const pipelineLabel = compactPipelineLabel(selectedExample?.label ?? selectedExample?.key ?? "loading");

  const statusLabel = isConnected ? "Live" : isConnecting ? "Connecting" : "Ready";
  const demoCaption = isConnected
    ? 'user: "book me a table for four at 7" -> agent responding'
    : 'user: "book me a table for four at 7" -> ready';

  return (
    <section className="live-demo-hero" aria-label="Nemotron Voice Agent live demo">
      <div className="live-demo-copy">
        <div className="live-demo-title-row">
          <h2>NVIDIA Nemotron Voice Agent</h2>
          <span className="shine-badge">LIVE UI MOCK</span>
        </div>
        <p>
          Build a sub-second, interruptible voice agent for cloud, on-prem, and edge.
        </p>
        <div className="mock-badges" aria-label="Blueprint summary">
          <span><b>release</b> v2.0</span>
          <span><b>transport</b> {selectedTransport.toUpperCase()}</span>
          <span><b>pipeline</b> {pipelineLabel}</span>
          <span><b>latency</b> {displayLatency === undefined ? "capturing" : formatLatency(displayLatency)}</span>
        </div>
      </div>

      <div className="live-demo-card">
        <div className="live-demo-scene" aria-live="polite">
          <div className="live-demo-caption">{demoCaption}</div>
          <div className="live-demo-waves" aria-hidden="true">
            {WAVE_BARS.map((bar) => <span key={bar} />)}
          </div>
          <div className="live-demo-play" aria-hidden="true">{statusLabel}</div>
          <div className={`live-latency-pill ${displayLatency === undefined ? "live-latency-pill--empty" : ""}`}>
            {displayLatency === undefined ? "Awaiting live latency" : `${formatLatency(displayLatency)} ${latencyLabel}`}
          </div>
        </div>

        <div className="live-latency-grid" aria-label="Live latency summary">
          <div>
            <span>First audio</span>
            <strong>{formatLatency(latestFirstAudioLatency)}</strong>
          </div>
          <div>
            <span>Turn latency</span>
            <strong>{formatLatency(latestTurnLatency)}</strong>
          </div>
          <div>
            <span>Median turn</span>
            <strong>{formatLatency(medianTurnLatency)}</strong>
          </div>
          <div>
            <span>Samples</span>
            <strong>{samples.length}</strong>
          </div>
        </div>
      </div>
    </section>
  );
}
