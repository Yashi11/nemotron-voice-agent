// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useState, useCallback } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";
import { TTFBChart } from "./TTFBChart";

interface TokenMetrics {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

interface TTFBMetric {
  processor: string;
  value: number;
  timestamp: string;
}

interface LatencyPoint {
  value: number;
  timestamp: string;
  first: boolean;
}

export function MetricsPanel() {
  const [tokens, setTokens] = useState<TokenMetrics>({ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 });
  const [ttfbHistory, setTtfbHistory] = useState<TTFBMetric[]>([]);
  const [latencyHistory, setLatencyHistory] = useState<LatencyPoint[]>([]);

  useRTVIClientEvent(
    RTVIEvent.Metrics,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useCallback((metrics: any) => {
      if (metrics.tokens && metrics.tokens.length > 0) {
        const t = metrics.tokens[0];
        setTokens({
          prompt_tokens: t.prompt_tokens || 0,
          completion_tokens: t.completion_tokens || 0,
          total_tokens: t.total_tokens || 0,
        });
      }

      if (metrics.ttfb && metrics.ttfb.length > 0) {
        const newEntries = metrics.ttfb.map((ttfb: { processor: string; value?: number }) => ({
          processor: ttfb.processor,
          value: (ttfb.value ?? 0) * 1000,
          timestamp: new Date().toLocaleTimeString()
        }));
        setTtfbHistory((prev) => [...prev, ...newEntries].slice(-10));
      }

    }, [])
  );

  useRTVIClientEvent(
    RTVIEvent.ServerMessage,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useCallback((message: any) => {
      if (message?.type === "user-bot-latency") {
        setLatencyHistory((prev) => [
          ...prev,
          {
            value: (message.latency ?? 0) * 1000,
            timestamp: new Date().toLocaleTimeString(),
            first: message.first ?? false,
          },
        ].slice(-10));
      }
    }, [])
  );

  return (
    <div className="metrics-panel p-4">
      {/* Token Usage */}
      <div className="metrics-section">
        <h3 className="metrics-title">Token Usage</h3>
        <div className="metrics-grid">
          <div className="metric-card">
            <span className="metric-label">Prompt Tokens</span>
            <span className="metric-value">{tokens.prompt_tokens}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Completion Tokens</span>
            <span className="metric-value">{tokens.completion_tokens}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Total Tokens</span>
            <span className="metric-value">{tokens.total_tokens}</span>
          </div>
        </div>
      </div>

      {/* User→Bot Latency */}
      <div className="metrics-section">
        <h3 className="metrics-title">User→Bot Latency</h3>
        {latencyHistory.length >= 2 ? (
          <TTFBChart data={latencyHistory} title="Response Latency" label="Latency" />
        ) : (
          <p className="text-secondary">No latency data yet. Start a conversation.</p>
        )}
      </div>

      {/* TTFB Metrics */}
      <div className="metrics-section">
        <h3 className="metrics-title">TTFB Metrics</h3>
        {ttfbHistory.length >= 2 ? (
          <TTFBChart data={ttfbHistory} title="NvidiaLLMService#0" />
        ) : (
          <p className="text-secondary">No TTFB data yet. Start a conversation.</p>
        )}
      </div>
    </div>
  );
}
