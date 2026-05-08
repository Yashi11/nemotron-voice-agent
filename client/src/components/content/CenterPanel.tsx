// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useState } from "react";
import { useConnectionState } from "../../hooks/useConnectionState";
import { useConversationMessages } from "../../hooks/useConversationMessages";
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

  return (
    <main className="flex-1 d-flex flex-col overflow-hidden">
      <div className="tab-header">
        {ALL_TABS.map((tab) => (
          <button
            key={tab.id}
            className={`tab-btn ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className={`flex-1 min-h-0 relative ${activeTab !== "conversation" ? "hidden" : ""}`}>
        <div className="conversation-overlay overflow-y-auto scrollbar-custom">
          <ConversationContent />
        </div>
      </div>
      <div className={`flex-1 min-h-0 overflow-y-auto scrollbar-custom ${activeTab !== "metrics" ? "hidden" : ""}`}>
        <MetricsPanel />
      </div>
      <div className={`flex-1 min-h-0 overflow-y-auto scrollbar-custom ${activeTab !== "services" ? "hidden" : ""}`}>
        <ServicesPanel />
      </div>
      <div className={`flex-1 min-h-0 overflow-y-auto scrollbar-custom ${activeTab !== "prompts" ? "hidden" : ""}`}>
        <PromptsPanel />
      </div>
    </main>
  );
}
