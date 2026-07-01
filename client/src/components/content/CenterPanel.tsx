// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useLayoutEffect, useRef, useState } from "react";
import { useConnectionState } from "../../hooks/useConnectionState";
import { IdleHero } from "./IdleHero";
import { ConversationPanel } from "./ConversationPanel";
import { MetricsPanel } from "./MetricsPanel";
import { ServicesPanel } from "./ServicesPanel";
import { PromptsPanel } from "./PromptsPanel";
import { ToolsPanel } from "./ToolsPanel";

type Tab = "conversation" | "metrics" | "services" | "prompts" | "tools";

const ALL_TABS: { id: Tab; label: string }[] = [
  { id: "conversation", label: "CONVERSATION" },
  { id: "metrics", label: "METRICS" },
  { id: "services", label: "SERVICES" },
  { id: "prompts", label: "PROMPTS" },
  { id: "tools", label: "TOOLS" },
];

function ConversationContent() {
  const { isConnected, isConnecting } = useConnectionState();

  if (!isConnected) {
    return <IdleHero connecting={isConnecting} fadingOut={false} />;
  }

  return (
    <ConversationPanel />
  );
}

export function CenterPanel() {
  const [activeTab, setActiveTab] = useState<Tab>("conversation");
  const conversationScrollRef = useRef<HTMLDivElement>(null);
  const { isConnected } = useConnectionState();

  useLayoutEffect(() => {
    if (activeTab !== "conversation" || isConnected) return;
    conversationScrollRef.current?.scrollTo({ top: 0, left: 0 });
  }, [activeTab, isConnected]);

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
        <div ref={conversationScrollRef} className="conversation-overlay overflow-y-auto">
          <ConversationContent />
        </div>
      </div>
      <div className={`flex-1 min-h-0 overflow-y-auto ${activeTab !== "metrics" ? "hidden" : ""}`}>
        <MetricsPanel />
      </div>
      <div className={`flex-1 min-h-0 overflow-y-auto ${activeTab !== "services" ? "hidden" : ""}`}>
        <ServicesPanel />
      </div>
      <div className={`flex-1 min-h-0 overflow-y-auto ${activeTab !== "prompts" ? "hidden" : ""}`}>
        <PromptsPanel />
      </div>
      <div className={`flex-1 min-h-0 overflow-y-auto ${activeTab !== "tools" ? "hidden" : ""}`}>
        <ToolsPanel />
      </div>
    </main>
  );
}
