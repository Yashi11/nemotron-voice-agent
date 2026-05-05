// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useState, useCallback, useRef } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";

export interface Message {
  id: string;
  role: "user" | "bot";
  text: string;
  timestamp: string;
}

let messageIdCounter = 0;
const generateId = () => `msg-${++messageIdCounter}-${Date.now()}`;

const appendTranscriptText = (current: string, next: string) => {
  const trimmedNext = next.trim();
  if (!trimmedNext) return current;
  return current ? `${current.trimEnd()} ${trimmedNext}` : trimmedNext;
};

export function useConversationMessages() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [userStreaming, setUserStreaming] = useState("");
  const [botStreaming, setBotStreaming] = useState("");
  const [userTimestamp, setUserTimestamp] = useState("");
  const [botTimestamp, setBotTimestamp] = useState("");

  const botTextRef = useRef("");
  const botProcessingRef = useRef(false);
  const botStartTimeRef = useRef("");
  const userTextRef = useRef("");
  const userInterimRef = useRef("");
  const userProcessingRef = useRef(false);
  const userStoppedRef = useRef(false);
  const userFinalizeTimeoutRef = useRef<number | undefined>(undefined);
  const userStartTimeRef = useRef("");

  const clearUserFinalizeTimeout = useCallback(() => {
    if (userFinalizeTimeoutRef.current === undefined) return;
    window.clearTimeout(userFinalizeTimeoutRef.current);
    userFinalizeTimeoutRef.current = undefined;
  }, []);

  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => {
      clearUserFinalizeTimeout();
      setMessages([]);
      setUserStreaming("");
      setBotStreaming("");
      botTextRef.current = "";
      botProcessingRef.current = false;
      botStartTimeRef.current = "";
      userTextRef.current = "";
      userInterimRef.current = "";
      userProcessingRef.current = false;
      userStoppedRef.current = false;
      userStartTimeRef.current = "";
      setUserTimestamp("");
      setBotTimestamp("");
    }, [clearUserFinalizeTimeout])
  );

  const finalizeUserMessage = useCallback(() => {
    clearUserFinalizeTimeout();
    if (!userProcessingRef.current) return;
    userProcessingRef.current = false;
    const finalText = (userTextRef.current || userInterimRef.current).trim();
    if (finalText) {
      setMessages((prev) => [...prev, {
        id: generateId(),
        role: "user",
        text: finalText,
        timestamp: userStartTimeRef.current || new Date().toISOString(),
      }]);
    }
    userTextRef.current = "";
    userInterimRef.current = "";
    userStoppedRef.current = false;
    userStartTimeRef.current = "";
    setUserTimestamp("");
    setUserStreaming("");
  }, [clearUserFinalizeTimeout]);

  const scheduleFinalizeUserMessage = useCallback(() => {
    clearUserFinalizeTimeout();
    userFinalizeTimeoutRef.current = window.setTimeout(finalizeUserMessage, 250);
  }, [clearUserFinalizeTimeout, finalizeUserMessage]);

  useRTVIClientEvent(
    RTVIEvent.UserStartedSpeaking,
    useCallback(() => {
      finalizeUserMessage();
      const now = new Date().toISOString();
      userTextRef.current = "";
      userInterimRef.current = "";
      userProcessingRef.current = true;
      userStoppedRef.current = false;
      userStartTimeRef.current = now;
      setUserTimestamp(now);
      setUserStreaming("");
    }, [finalizeUserMessage])
  );

  useRTVIClientEvent(
    RTVIEvent.UserTranscript,
    useCallback((data: { final: boolean; text: string }) => {
      userProcessingRef.current = true;
      if (data.final) {
        userTextRef.current = appendTranscriptText(userTextRef.current, data.text);
        userInterimRef.current = userTextRef.current;
        setUserStreaming(userTextRef.current);
      } else {
        const interimText = appendTranscriptText(userTextRef.current, data.text);
        userInterimRef.current = interimText;
        setUserStreaming(interimText);
      }
      if (userStoppedRef.current) scheduleFinalizeUserMessage();
    }, [scheduleFinalizeUserMessage])
  );

  useRTVIClientEvent(
    RTVIEvent.UserStoppedSpeaking,
    useCallback(() => {
      userStoppedRef.current = true;
      scheduleFinalizeUserMessage();
    }, [scheduleFinalizeUserMessage])
  );

  useRTVIClientEvent(
    RTVIEvent.BotStartedSpeaking,
    useCallback(() => {
      const now = new Date().toISOString();
      botStartTimeRef.current = now;
      setBotTimestamp(now);
    }, [])
  );

  useRTVIClientEvent(
    RTVIEvent.BotLlmText,
    useCallback((data: { text: string }) => {
      botProcessingRef.current = true;
      botTextRef.current += data.text;
      setBotStreaming(botTextRef.current);
    }, [])
  );

  const finalizeBotMessage = useCallback(() => {
    if (!botProcessingRef.current) return;
    botProcessingRef.current = false;
    const finalText = botTextRef.current.trim();
    if (finalText) {
      setMessages((prev) => [...prev, {
        id: generateId(),
        role: "bot",
        text: finalText,
        timestamp: botStartTimeRef.current || new Date().toISOString(),
      }]);
    }
    botTextRef.current = "";
    botStartTimeRef.current = "";
    setBotTimestamp("");
    setBotStreaming("");
  }, []);

  useRTVIClientEvent(RTVIEvent.BotLlmStopped, finalizeBotMessage);
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, finalizeBotMessage);

  return {
    messages,
    userStreaming,
    botStreaming,
    userTimestamp,
    botTimestamp,
  };
}
