// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import type { Message } from "../../hooks/useConversationMessages";
import { TranscriptMessage } from "./TranscriptMessage";

interface ConversationPanelProps {
  messages: Message[];
  userStreaming: string;
  botStreaming: string;
  userTimestamp: string;
  botTimestamp: string;
}

export function ConversationPanel({ messages, userStreaming, botStreaming, userTimestamp, botTimestamp }: Readonly<ConversationPanelProps>) {
  return (
    <div className="p-4">
      <ul className="d-flex flex-col gap-2" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {messages.map((msg) => (
          <TranscriptMessage
            key={msg.id}
            role={msg.role}
            text={msg.text}
            timestamp={msg.timestamp}
          />
        ))}
        {userStreaming && (
          <TranscriptMessage
            role="user"
            text={userStreaming}
            timestamp={userTimestamp || new Date().toISOString()}
            streaming
          />
        )}
        {botStreaming && (
          <TranscriptMessage
            role="bot"
            text={botStreaming}
            timestamp={botTimestamp || new Date().toISOString()}
            streaming
          />
        )}
      </ul>
    </div>
  );
}
