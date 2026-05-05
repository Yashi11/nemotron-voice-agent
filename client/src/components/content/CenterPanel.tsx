// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useState } from "react";
import { useConnectionState } from "../../hooks/useConnectionState";
import { useConversationMessages } from "../../hooks/useConversationMessages";
import { useApp } from "../../context/useApp";
import { IdleHero } from "./IdleHero";
import { ConversationPanel } from "./ConversationPanel";
import { MetricsPanel } from "./MetricsPanel";
import { ServicesPanel } from "./ServicesPanel";
import { PromptsPanel } from "./PromptsPanel";

type Tab = "conversation" | "metrics" | "services" | "prompts";

const ALL_TABS: { id: Tab; label: string }[] = [
  { id: "conversation", label: "CONVERSATION" },
  { id: "metrics", label: "METRICS" },
  { id: "services", label: "SERVICES" },
  { id: "prompts", label: "PROMPTS" },
];

function ConversationContent() {
  const { isConnected, isConnecting } = useConnectionState();
  const conversation = useConversationMessages();

  return (
    <>
      <ConversationPanel {...conversation} />
      {!isConnected && (
        <div className="idle-hero-overlay">
          <IdleHero connecting={isConnecting} fadingOut={false} />
        </div>
      )}
    </>
  );
}

export function CenterPanel() {
  const [activeTab, setActiveTab] = useState<Tab>("conversation");
  const { pipelineMode, cascadedSubMode } = useApp();
  const isAgenticAirline = pipelineMode === "cascaded" && cascadedSubMode === "agentic_airline";
  const tabs = isAgenticAirline ? ALL_TABS.filter((t) => t.id !== "prompts") : ALL_TABS;
  const effectiveTab: Tab = isAgenticAirline && activeTab === "prompts" ? "conversation" : activeTab;

  return (
    <main className="flex-1 d-flex flex-col overflow-hidden">
      <div className="tab-header">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab-btn ${effectiveTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className={`flex-1 min-h-0 relative ${effectiveTab !== "conversation" ? "hidden" : ""}`}>
        <div className="conversation-overlay overflow-y-auto scrollbar-custom">
          <ConversationContent />
        </div>
      </div>
      <div className={`flex-1 min-h-0 overflow-y-auto scrollbar-custom ${effectiveTab !== "metrics" ? "hidden" : ""}`}>
        <MetricsPanel />
      </div>
      <div className={`flex-1 min-h-0 overflow-y-auto scrollbar-custom ${effectiveTab !== "services" ? "hidden" : ""}`}>
        <ServicesPanel />
      </div>
      {!isAgenticAirline && (
        <div className={`flex-1 min-h-0 overflow-y-auto scrollbar-custom ${effectiveTab !== "prompts" ? "hidden" : ""}`}>
          <PromptsPanel />
        </div>
      )}
    </main>
  );
}
