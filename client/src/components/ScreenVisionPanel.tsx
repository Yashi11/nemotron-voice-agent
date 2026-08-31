// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { useCallback, useEffect, useRef, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { usePipecatClient, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { uploadScreenCapture, uploadScreenFrame } from "../api";
import { isRecord, stringField } from "../utils";

type ScreenStatus = "idle" | "starting" | "live" | "error";
type ScreenAgentUpdate = { observation: string; focus: string };

const FRAME_INTERVAL_MS = 1500;
const FRAME_MAX_WIDTH = 1280;
const HIGHRES_JPEG_QUALITY = 0.92;

function canvasToJpegBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Could not encode screen frame"))), "image/jpeg", 0.75);
  });
}

function isExpiredSessionError(error: unknown): boolean {
  return error instanceof Error && error.message.startsWith("HTTP 404");
}

export function ScreenVisionPanel({ sessionId }: Readonly<{ sessionId: string }>) {
  const client = usePipecatClient();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const [enabled, setEnabled] = useState(false);
  const [status, setStatus] = useState<ScreenStatus>("idle");
  const [error, setError] = useState("");
  const [agentUpdate, setAgentUpdate] = useState<ScreenAgentUpdate | null>(null);

  const sendState = useCallback((isEnabled: boolean) => {
    if (!client || client.state !== "ready") return;
    try {
      client.sendClientMessage("screen-state", { enabled: isEnabled });
    } catch (err) {
      console.warn("Could not send screen-share state update:", err);
    }
  }, [client]);

  const expireSession = useCallback(() => {
    if (intervalRef.current !== null) window.clearInterval(intervalRef.current);
    intervalRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    sendState(false);
    setEnabled(false);
    setAgentUpdate(null);
    setStatus("error");
    setError("Your voice session expired. Reconnect before sharing your screen again.");
  }, [sendState]);

  const uploadFrame = useCallback(async () => {
    if (!sessionId || inFlightRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth || !video.videoHeight) return;
    const scale = Math.min(1, FRAME_MAX_WIDTH / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    inFlightRef.current = true;
    try {
      await uploadScreenFrame(sessionId, await canvasToJpegBlob(canvas));
      setError("");
    } catch (err) {
      if (isExpiredSessionError(err)) {
        expireSession();
        return;
      }
      setStatus("error");
      setError(err instanceof Error ? err.message : "Screen upload failed");
    } finally {
      inFlightRef.current = false;
    }
  }, [expireSession, sessionId]);

  const captureScreenDetail = useCallback(async (requestId: string) => {
    if (!requestId || !sessionId) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth || !video.videoHeight) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    try {
      setStatus("starting");
      await uploadScreenCapture(sessionId, await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Could not encode screen capture"))), "image/jpeg", HIGHRES_JPEG_QUALITY);
      }), requestId);
      setStatus("live");
      setError("");
    } catch (err) {
      if (isExpiredSessionError(err)) {
        expireSession();
        return;
      }
      setStatus("error");
      setError(err instanceof Error ? err.message : "Screen detail capture failed");
    }
  }, [expireSession, sessionId]);

  const stop = useCallback(() => {
    if (intervalRef.current !== null) window.clearInterval(intervalRef.current);
    intervalRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    sendState(false);
    setEnabled(false);
    setAgentUpdate(null);
    setStatus("idle");
  }, [sendState]);

  const start = useCallback(async () => {
    if (enabled) {
      stop();
      return;
    }
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setStatus("error");
      setError("Browser display capture is not available.");
      return;
    }
    setStatus("starting");
    setError("");
    setAgentUpdate(null);
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) throw new Error("Screen preview is not ready.");
      video.srcObject = stream;
      await video.play();
      stream.getVideoTracks().forEach((track) => track.addEventListener("ended", stop, { once: true }));
      setEnabled(true);
      setStatus("live");
      sendState(true);
      void uploadFrame();
      intervalRef.current = window.setInterval(() => void uploadFrame(), FRAME_INTERVAL_MS);
    } catch (err) {
      stop();
      setStatus("error");
      setError(err instanceof Error ? err.message : "Could not start screen sharing");
    }
  }, [enabled, sendState, stop, uploadFrame]);

  useEffect(() => stop, [stop]);

  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => stop(), [stop])
  );
  useRTVIClientEvent(
    RTVIEvent.ServerMessage,
    useCallback((message: unknown) => {
      if (!isRecord(message) || stringField(message, "type") !== "screen-agent-update") return;
      const observation = stringField(message, "observation");
      if (observation) setAgentUpdate({ observation, focus: stringField(message, "focus") });
    }, [])
  );
  useRTVIClientEvent(
    RTVIEvent.ServerMessage,
    useCallback((message: unknown) => {
      if (!isRecord(message) || stringField(message, "type") !== "screen-capture-request") return;
      void captureScreenDetail(stringField(message, "request_id"));
    }, [captureScreenDetail])
  );

  return (
    <div className={`webcam-control webcam-control-${status} ${enabled ? "webcam-control-enabled" : "webcam-control-off"}`}>
      <div className="webcam-control-main">
        <button className="btn-icon webcam-icon-button" type="button" onClick={() => void start()} title={enabled ? "Stop screen vision" : "Start screen vision"} aria-label={enabled ? "Stop screen vision" : "Start screen vision"}>
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 5h16v11H4z" /><path d="M8 19h8" /><path d="M12 16v3" /></svg>
        </button>
        <div className="webcam-control-text">
          <strong><span className={`webcam-status-dot${enabled ? " webcam-status-dot-live" : ""}`} aria-hidden="true" />{enabled ? "Screen vision enabled" : "Screen share off"}</strong>
          <small className="webcam-status-label">{enabled ? "Sampling the display you chose" : "Choose a display to share"}</small>
          {error && <small className="webcam-error">{error}</small>}
        </div>
      </div>
      <div className={`webcam-preview${enabled ? "" : " hidden"}`}>
        <video ref={videoRef} muted playsInline />
      </div>
      <canvas ref={canvasRef} className="hidden" />
      <small className="webcam-privacy-note">Only the selected display is sampled while sharing. Cursor location may not be available.</small>
      {agentUpdate && <div className="webcam-agent-observation"><strong>Latest screen view</strong><p>{agentUpdate.observation}</p>{agentUpdate.focus && <small>{agentUpdate.focus}</small>}</div>}
    </div>
  );
}
