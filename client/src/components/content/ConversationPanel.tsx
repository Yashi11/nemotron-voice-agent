// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatConversation,
  useRTVIClientEvent,
  filterEmptyMessages,
  type ConversationMessage,
  type ConversationMessagePart,
} from "@pipecat-ai/client-react";
import { TranscriptMessage } from "./TranscriptMessage";

const renderPartText = (part: ConversationMessagePart): string => {
  const { text } = part;
  if (text === null || text === undefined) return "";
  if (typeof text === "string") return text;
  if (typeof text === "number" || typeof text === "boolean") return String(text);
  if (
    typeof text === "object" &&
    text !== null &&
    "spoken" in text &&
    "unspoken" in text
  ) {
    const { spoken, unspoken } = text as { spoken: string; unspoken: string };
    return `${spoken}${unspoken}`;
  }
  return "";
};

const renderMessageText = (message: ConversationMessage): string =>
  message.parts.map(renderPartText).join("");

const isUserOrAssistant = (m: ConversationMessage) =>
  m.role === "user" || m.role === "assistant";

const findLatestUserMessage = (messages: ConversationMessage[]) => {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === "user") return messages[i];
  }
  return undefined;
};

const findUserMessageByCreatedAt = (messages: ConversationMessage[], createdAt?: string | null) => {
  if (!createdAt) return undefined;
  return messages.find((message) => message.role === "user" && message.createdAt === createdAt);
};

const normalizeTranscript = (text?: string | null) => (text ?? "").trim().replace(/\s+/g, " ");

const findUserMessageByTranscript = (
  messages: ConversationMessage[],
  transcript: string | null | undefined,
  finalizedCreatedAts: Set<string>
) => {
  const normalizedTranscript = normalizeTranscript(transcript);
  if (!normalizedTranscript) return undefined;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.role !== "user") continue;
    if (message.final || finalizedCreatedAts.has(message.createdAt)) continue;
    if (normalizeTranscript(renderMessageText(message)) === normalizedTranscript) return message;
  }
  return undefined;
};

export function ConversationPanel() {
  const { messages } = usePipecatConversation();

  const visibleMessages = useMemo(
    () => filterEmptyMessages(messages).filter(isUserOrAssistant),
    [messages]
  );

  const [currentUserTurnActive, setCurrentUserTurnActive] = useState(false);

  const [serverFinalizedUserCreatedAts, setServerFinalizedUserCreatedAts] =
    useState<Set<string>>(new Set());

  const visibleMessagesRef = useRef<ConversationMessage[]>(visibleMessages);
  useEffect(() => {
    visibleMessagesRef.current = visibleMessages;
  }, [visibleMessages]);

  useRTVIClientEvent(
    RTVIEvent.UserStartedSpeaking,
    useCallback(() => {
      setCurrentUserTurnActive(true);
    }, [])
  );

  useRTVIClientEvent(
    RTVIEvent.ServerMessage,
    useCallback((message: { type?: string; timestamp?: string | null; transcript?: string | null }) => {
      if (message?.type !== "user-turn-finalized") return;
      setCurrentUserTurnActive(false);
      setServerFinalizedUserCreatedAts((prev) => {
        const finalizedUser =
          findUserMessageByCreatedAt(visibleMessagesRef.current, message.timestamp) ??
          findUserMessageByTranscript(visibleMessagesRef.current, message.transcript, prev) ??
          findLatestUserMessage(visibleMessagesRef.current);
        if (!finalizedUser || prev.has(finalizedUser.createdAt)) return prev;
        const next = new Set(prev);
        next.add(finalizedUser.createdAt);
        return next;
      });
    }, [])
  );

  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => {
      setCurrentUserTurnActive(false);
      setServerFinalizedUserCreatedAts(new Set());
    }, [])
  );

  const latestUserCreatedAt = useMemo(
    () => findLatestUserMessage(visibleMessages)?.createdAt,
    [visibleMessages]
  );

  const computeStreaming = (message: ConversationMessage): boolean => {
    if (message.role !== "user") return !message.final;
    if (message.final) return false;
    if (serverFinalizedUserCreatedAts.has(message.createdAt)) return false;
    const isLatestUser = message.createdAt === latestUserCreatedAt;
    return isLatestUser && currentUserTurnActive;
  };

  return (
    <div className="p-4">
      <ul className="d-flex flex-col gap-2" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {visibleMessages.map((msg, idx) => (
          <TranscriptMessage
            key={`${msg.createdAt}-${idx}`}
            role={msg.role === "assistant" ? "bot" : "user"}
            text={renderMessageText(msg)}
            timestamp={msg.createdAt}
            streaming={computeStreaming(msg)}
          />
        ))}
      </ul>
    </div>
  );
}
