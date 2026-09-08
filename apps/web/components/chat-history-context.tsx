"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { ChatThreadSummary } from "@/lib/types";
import { mergeChatHistory } from "@/lib/chat-history-merge";

type ChatHistoryContextValue = {
  threads: ChatThreadSummary[];
  historyLoadState: "loading" | "ready" | "preview" | "unavailable";
  reloadHistory: () => void;
  notification?: { latestEventId?: string; occurredAt?: string };
  activeThreadId?: string;
  setActiveThreadId: (threadId?: string) => void;
  upsertThread: (thread: ChatThreadSummary) => void;
  removeThread: (threadId: string) => void;
};

const ChatHistoryContext = createContext<ChatHistoryContextValue | undefined>(undefined);

export function ChatHistoryProvider({
  children,
  initialThreads,
  initialLoadState,
}: {
  children: ReactNode;
  initialThreads: ChatThreadSummary[];
  initialLoadState: "loading" | "ready" | "preview" | "unavailable";
}) {
  const [threads, setThreads] = useState(initialThreads);
  const [activeThreadId, setActiveThreadId] = useState<string>();
  const [historyLoadState, setHistoryLoadState] = useState(initialLoadState);
  const [notification, setNotification] = useState<ChatHistoryContextValue["notification"]>();
  const [revision, setRevision] = useState(0);
  const changedIds = useRef(new Set<string>());
  const reloadHistory = useCallback(() => {
    setHistoryLoadState("loading");
    setRevision((value) => value + 1);
  }, []);

  useEffect(() => {
    if (initialLoadState !== "loading" && revision === 0) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20_000);
    let active = true;
    fetch("/api/portal/sidebar", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Sidebar unavailable");
        const data = await response.json();
        if (!active) return;
        if (!Array.isArray(data.threads) || !["ready", "preview", "unavailable"].includes(data.historyLoadState)) {
          throw new Error("Invalid sidebar response");
        }
        if (data.historyLoadState !== "unavailable") {
          setThreads((current) => mergeChatHistory(current, data.threads, changedIds.current));
        }
        setNotification(data.notification);
        setHistoryLoadState(data.historyLoadState);
      })
      .catch(() => { if (active) setHistoryLoadState("unavailable"); })
      .finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [initialLoadState, revision]);

  const upsertThread = useCallback((thread: ChatThreadSummary) => {
    changedIds.current.add(thread.id);
    setThreads((current) => [thread, ...current.filter((item) => item.id !== thread.id)]);
  }, []);

  const removeThread = useCallback((threadId: string) => {
    changedIds.current.add(threadId);
    setThreads((current) => current.filter((thread) => thread.id !== threadId));
  }, []);

  const value = useMemo(() => ({
    threads,
    historyLoadState,
    reloadHistory,
    notification,
    activeThreadId,
    setActiveThreadId,
    upsertThread,
    removeThread,
  }), [activeThreadId, historyLoadState, notification, reloadHistory, removeThread, threads, upsertThread]);

  return <ChatHistoryContext.Provider value={value}>{children}</ChatHistoryContext.Provider>;
}

export function useChatHistory() {
  const value = useContext(ChatHistoryContext);
  if (!value) throw new Error("useChatHistory must be used inside ChatHistoryProvider");
  return value;
}
