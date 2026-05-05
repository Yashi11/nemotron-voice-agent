// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import {
  useState,
  useCallback,
  useMemo,
  type ReactNode,
} from "react";
import { useDeployment, useDefaultLLMs, useDefaultPrompts, useDefaultASR, useDefaultTTS, type LLMService, type Prompt, type SimpleService } from "../api";
import { readLSArray, readLSString, writeLSString, writeLSJson, removeLSKey } from "../utils";
import { AppContext } from "./app-context";

export type PipelineMode = "cascaded" | "s2s";
export type CascadedSubMode = "simple" | "agentic_airline";
export type TransportType = "webrtc" | "websocket";

const ASR_STORAGE = "nvidia-voice-agent-asr-custom";
const TTS_STORAGE = "nvidia-voice-agent-tts-custom";
const LLM_STORAGE = "nvidia-voice-agent-llm-custom";
const ASR_SELECTION_STORAGE = "nvidia-voice-agent-asr-selection";
const TTS_SELECTION_STORAGE = "nvidia-voice-agent-tts-selection";
const LLM_SELECTION_STORAGE = "nvidia-voice-agent-llm-selection";
const PROMPT_STORAGE = "nvidia-voice-agent-prompts-custom";
const PROMPT_SELECTION = "nvidia-voice-agent-prompt-selection";
const TRANSPORT_STORAGE = "nvidia-voice-agent-transport";
const PIPELINE_MODE_STORAGE = "nvidia-voice-agent-pipeline-mode";
const CASCADED_SUB_MODE_STORAGE = "nvidia-voice-agent-cascaded-sub-mode";

type ManagedService = {
  id: string;
  builtIn: boolean;
};

function readCustomServices<T extends ManagedService>(key: string): T[] {
  return readLSArray<T>(key, []).map((service) => ({ ...service, builtIn: false }));
}

function getEffectiveSelectedId<T extends ManagedService>(
  selectedId: string,
  items: T[],
  loading: boolean,
): string {
  if (selectedId && items.some((item) => item.id === selectedId)) return selectedId;
  if (loading) return "";
  return items.find((item) => item.builtIn)?.id || items[0]?.id || "";
}

type ManagedServiceCatalogOptions<T extends ManagedService> = {
  defaultItems: T[];
  loading: boolean;
  customStorageKey: string;
  selectionStorageKey: string;
};

function useManagedServiceCatalog<T extends ManagedService>({
  defaultItems,
  loading,
  customStorageKey,
  selectionStorageKey,
}: ManagedServiceCatalogOptions<T>) {
  const [customItems, setCustomItems] = useState<T[]>(() => readCustomServices<T>(customStorageKey));
  const [selectedId, setSelectedId] = useState(() => readLSString(selectionStorageKey));

  const items = useMemo(() => [...defaultItems, ...customItems], [defaultItems, customItems]);

  const effectiveSelectedId = useMemo(
    () => getEffectiveSelectedId(selectedId, items, loading),
    [selectedId, items, loading],
  );

  const select = useCallback((id: string) => {
    setSelectedId(id);
    writeLSString(selectionStorageKey, id);
  }, [selectionStorageKey]);

  const persistCustom = useCallback((next: T[]) => {
    setCustomItems(next);
    writeLSJson(customStorageKey, next);
  }, [customStorageKey]);

  const clearSelection = useCallback(() => {
    setSelectedId("");
    removeLSKey(selectionStorageKey);
  }, [selectionStorageKey]);

  const removeCustom = useCallback((id: string) => {
    persistCustom(customItems.filter((item) => item.id !== id));
    if (effectiveSelectedId === id) {
      clearSelection();
    }
  }, [clearSelection, customItems, effectiveSelectedId, persistCustom]);

  const selected = useMemo(
    () => items.find((item) => item.id === effectiveSelectedId),
    [items, effectiveSelectedId],
  );

  return {
    customItems,
    items,
    selected,
    selectedId: effectiveSelectedId,
    select,
    persistCustom,
    removeCustom,
  };
}

export interface AppState {
  pipelineMode: PipelineMode;
  setPipelineMode: (m: PipelineMode) => void;

  cascadedSubMode: CascadedSubMode;
  setCascadedSubMode: (m: CascadedSubMode) => void;
  agenticAirlineAvailable: boolean;

  /** When false, the server pinned a single bot — clients must not let the user switch modes. */
  deploymentSelectable: boolean;

  selectedTransport: TransportType;
  setTransport: (t: TransportType) => void;

  selectedS2SServer: string;
  setSelectedS2SServer: (s: string) => void;

  llms: LLMService[];
  llmsLoading: boolean;
  selectedLLMId: string;
  selectLLM: (id: string) => void;
  addLLM: (name: string, modelId: string, baseUrl: string, systemPrompt: string, extraParams: string) => LLMService;
  updateLLM: (id: string, updates: Partial<Omit<LLMService, "id" | "builtIn">>) => void;
  removeLLM: (id: string) => void;
  selectedLLM: LLMService | undefined;

  asrServices: SimpleService[];
  asrLoading: boolean;
  selectedASRId: string;
  selectASR: (id: string) => void;
  addASR: (name: string, server: string, model?: string) => SimpleService;
  updateASR: (id: string, updates: Partial<Omit<SimpleService, "id" | "builtIn">>) => void;
  removeASR: (id: string) => void;
  selectedASR: SimpleService | undefined;

  ttsServices: SimpleService[];
  ttsLoading: boolean;
  selectedTTSId: string;
  selectTTS: (id: string) => void;
  addTTS: (name: string, server: string, voiceId?: string) => SimpleService;
  updateTTS: (id: string, updates: Partial<Omit<SimpleService, "id" | "builtIn">>) => void;
  removeTTS: (id: string) => void;
  selectedTTS: SimpleService | undefined;

  selectedVoiceId: string;
  setSelectedVoiceId: (id: string) => void;

  prompts: Prompt[];
  promptsLoading: boolean;
  selectedPromptKey: string;
  selectPrompt: (key: string) => void;
  addPrompt: (key: string, description: string, content: string) => string | null;
  updatePrompt: (key: string, description: string, content: string) => void;
  removePrompt: (key: string) => void;
  selectedPrompt: Prompt | undefined;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const { data: deployment } = useDeployment();
  const deploymentLoaded = deployment !== undefined;
  const agenticAirlineAvailable = !deploymentLoaded
    || deployment.options.some((option) => option.pipelineMode === "agentic" || option.id === "agentic-airline");
  const deploymentSelectable = !deploymentLoaded || deployment.selectable;

  // --- Pipeline mode state ---
  const [pipelineMode, setPipelineModeRaw] = useState<PipelineMode>(() => {
    try { const v = localStorage.getItem(PIPELINE_MODE_STORAGE); if (v === "s2s" || v === "cascaded") return v as PipelineMode; } catch { /* ignore */ }
    return "cascaded";
  });
  const setPipelineMode = useCallback((m: PipelineMode) => {
    setPipelineModeRaw(m);
    writeLSString(PIPELINE_MODE_STORAGE, m);
  }, []);

  // --- Cascaded sub-mode state ---
  const [cascadedSubMode, setCascadedSubModeRaw] = useState<CascadedSubMode>(() => {
    try {
      const v = localStorage.getItem(CASCADED_SUB_MODE_STORAGE);
      if (v === "simple" || v === "agentic_airline") return v as CascadedSubMode;
    } catch { /* ignore */ }
    return "simple";
  });
  const setCascadedSubMode = useCallback((m: CascadedSubMode) => {
    setCascadedSubModeRaw(m);
    writeLSString(CASCADED_SUB_MODE_STORAGE, m);
  }, []);

  const pinnedMode = useMemo(() => {
    if (!deployment || deployment.selectable) return null;
    const activeMode = deployment.active.pipelineMode;
    if (activeMode === "s2s") return { pipeline: "s2s" as PipelineMode, sub: "simple" as CascadedSubMode };
    if (activeMode === "agentic") return { pipeline: "cascaded" as PipelineMode, sub: "agentic_airline" as CascadedSubMode };
    return { pipeline: "cascaded" as PipelineMode, sub: "simple" as CascadedSubMode };
  }, [deployment]);

  const effectivePipelineMode: PipelineMode = pinnedMode?.pipeline ?? pipelineMode;
  const effectiveCascadedSubMode: CascadedSubMode = pinnedMode?.sub
    ?? (deploymentLoaded && !agenticAirlineAvailable && cascadedSubMode === "agentic_airline"
        ? "simple"
        : cascadedSubMode);

  // --- Transport state ---
  const [selectedTransport, setSelectedTransport] = useState<TransportType>(() => {
    try { const v = localStorage.getItem(TRANSPORT_STORAGE); if (v === "websocket") return "websocket"; } catch { /* ignore */ }
    return "webrtc";
  });
  const setTransport = useCallback((t: TransportType) => {
    setSelectedTransport(t);
    writeLSString(TRANSPORT_STORAGE, t);
  }, []);

  // --- S2S server state ---
  const [selectedS2SServer, setSelectedS2SServer] = useState("");

  // --- LLM state ---
  const { data: defaultLLMs = [], isLoading: llmsLoading } = useDefaultLLMs();
  const {
    customItems: customLLMs,
    items: llms,
    selectedId: effectiveSelectedLLMId,
    select: selectLLM,
    persistCustom: persistLLMs,
    removeCustom: removeLLM,
    selected: selectedLLM,
  } = useManagedServiceCatalog<LLMService>({
    defaultItems: defaultLLMs,
    loading: llmsLoading,
    customStorageKey: LLM_STORAGE,
    selectionStorageKey: LLM_SELECTION_STORAGE,
  });

  const addLLM = useCallback((name: string, modelId: string, baseUrl: string, systemPrompt: string, extraParams: string) => {
    const svc: LLMService = { id: `custom-${crypto.randomUUID()}`, name, modelId, baseUrl, systemPrompt, extraParams, builtIn: false };
    persistLLMs([...customLLMs, svc]);
    return svc;
  }, [customLLMs, persistLLMs]);

  const updateLLM = useCallback((id: string, updates: Partial<Omit<LLMService, "id" | "builtIn">>) => {
    persistLLMs(customLLMs.map((s) => (s.id === id ? { ...s, ...updates } : s)));
  }, [customLLMs, persistLLMs]);

  // --- ASR state ---
  const { data: defaultASR = [], isLoading: asrLoading } = useDefaultASR();
  const {
    customItems: customASR,
    items: asrServices,
    selectedId: effectiveSelectedASRId,
    select: selectASR,
    persistCustom: persistASR,
    removeCustom: removeASR,
    selected: selectedASR,
  } = useManagedServiceCatalog<SimpleService>({
    defaultItems: defaultASR,
    loading: asrLoading,
    customStorageKey: ASR_STORAGE,
    selectionStorageKey: ASR_SELECTION_STORAGE,
  });

  const addASR = useCallback((name: string, server: string, model?: string) => {
    const svc: SimpleService = { id: `custom-asr-${crypto.randomUUID()}`, name, server, model, builtIn: false };
    persistASR([...customASR, svc]);
    return svc;
  }, [customASR, persistASR]);

  const updateASR = useCallback((id: string, updates: Partial<Omit<SimpleService, "id" | "builtIn">>) => {
    persistASR(customASR.map((s) => (s.id === id ? { ...s, ...updates } : s)));
  }, [customASR, persistASR]);

  const [selectedVoiceId, setSelectedVoiceId] = useState("");

  // --- TTS state ---
  const { data: defaultTTS = [], isLoading: ttsLoading } = useDefaultTTS();
  const {
    customItems: customTTS,
    items: ttsServices,
    selectedId: effectiveSelectedTTSId,
    select: selectTTSBase,
    persistCustom: persistTTS,
    removeCustom: removeTTS,
    selected: selectedTTS,
  } = useManagedServiceCatalog<SimpleService>({
    defaultItems: defaultTTS,
    loading: ttsLoading,
    customStorageKey: TTS_STORAGE,
    selectionStorageKey: TTS_SELECTION_STORAGE,
  });

  const selectTTS = useCallback((id: string) => {
    selectTTSBase(id);
    setSelectedVoiceId("");
  }, [selectTTSBase]);

  const addTTS = useCallback((name: string, server: string, voiceId?: string) => {
    const svc: SimpleService = { id: `custom-tts-${crypto.randomUUID()}`, name, server, voiceId, builtIn: false };
    persistTTS([...customTTS, svc]);
    return svc;
  }, [customTTS, persistTTS]);

  const updateTTS = useCallback((id: string, updates: Partial<Omit<SimpleService, "id" | "builtIn">>) => {
    persistTTS(customTTS.map((s) => (s.id === id ? { ...s, ...updates } : s)));
  }, [customTTS, persistTTS]);

  // --- Prompt state ---
  const { data: defaultPrompts = [], isLoading: promptsLoading } = useDefaultPrompts();
  const [customPrompts, setCustomPrompts] = useState<Prompt[]>(() => readLSArray<Prompt>(PROMPT_STORAGE, []).map((p) => ({ ...p, builtIn: false })));
  const [selectedPromptKey, setSelectedPromptKey] = useState(() => {
    try { return localStorage.getItem(PROMPT_SELECTION) || ""; } catch { return ""; }
  });

  const prompts = useMemo(() => [...defaultPrompts, ...customPrompts], [defaultPrompts, customPrompts]);

  const effectiveSelectedPromptKey = selectedPromptKey || prompts[0]?.key || "";

  const persistPrompts = useCallback((next: Prompt[]) => {
    setCustomPrompts(next);
    writeLSJson(PROMPT_STORAGE, next);
  }, []);

  const selectPrompt = useCallback((key: string) => {
    setSelectedPromptKey(key);
    writeLSString(PROMPT_SELECTION, key);
  }, []);

  const addPrompt = useCallback((key: string, description: string, content: string): string | null => {
    const slug = key.trim().toLowerCase().replace(/\s+/g, "_");
    if (prompts.some((p) => p.key === slug)) return `Prompt '${slug}' already exists`;
    persistPrompts([...customPrompts, { key: slug, description, content, builtIn: false }]);
    return null;
  }, [prompts, customPrompts, persistPrompts]);

  const updatePrompt = useCallback((key: string, description: string, content: string) => {
    persistPrompts(customPrompts.map((p) => (p.key === key ? { ...p, description, content } : p)));
  }, [customPrompts, persistPrompts]);

  const removePrompt = useCallback((key: string) => {
    persistPrompts(customPrompts.filter((p) => p.key !== key));
    if (effectiveSelectedPromptKey === key) setSelectedPromptKey("");
  }, [customPrompts, persistPrompts, effectiveSelectedPromptKey]);

  const selectedPrompt = useMemo(() => prompts.find((p) => p.key === effectiveSelectedPromptKey), [prompts, effectiveSelectedPromptKey]);

  const value = useMemo<AppState>(() => ({
    pipelineMode: effectivePipelineMode, setPipelineMode,
    cascadedSubMode: effectiveCascadedSubMode, setCascadedSubMode, agenticAirlineAvailable,
    deploymentSelectable,
    selectedTransport, setTransport,
    selectedS2SServer, setSelectedS2SServer,
    llms, llmsLoading, selectedLLMId: effectiveSelectedLLMId, selectLLM, addLLM, updateLLM, removeLLM, selectedLLM,
    asrServices, asrLoading, selectedASRId: effectiveSelectedASRId, selectASR, addASR, updateASR, removeASR, selectedASR,
    ttsServices, ttsLoading, selectedTTSId: effectiveSelectedTTSId, selectTTS, addTTS, updateTTS, removeTTS, selectedTTS,
    selectedVoiceId, setSelectedVoiceId,
    prompts, promptsLoading, selectedPromptKey: effectiveSelectedPromptKey, selectPrompt, addPrompt, updatePrompt, removePrompt, selectedPrompt,
  }), [effectivePipelineMode, setPipelineMode, effectiveCascadedSubMode, setCascadedSubMode, agenticAirlineAvailable, deploymentSelectable, selectedTransport, setTransport, selectedS2SServer,
       llms, llmsLoading, effectiveSelectedLLMId, selectLLM, addLLM, updateLLM, removeLLM, selectedLLM,
       asrServices, asrLoading, effectiveSelectedASRId, selectASR, addASR, updateASR, removeASR, selectedASR,
       ttsServices, ttsLoading, effectiveSelectedTTSId, selectTTS, addTTS, updateTTS, removeTTS, selectedTTS,
       selectedVoiceId,
       prompts, promptsLoading, effectiveSelectedPromptKey, selectPrompt, addPrompt, updatePrompt, removePrompt, selectedPrompt]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
