"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { ChatThreadSummary } from "@/lib/types";

type ChatHistoryContextValue = {
  threads: ChatThreadSummary[];
  historyLoadState: "ready" | "preview" | "unavailable";
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
  initialLoadState: "ready" | "preview" | "unavailable";
}) {
  const [threads, setThreads] = useState(initialThreads);
  const [activeThreadId, setActiveThreadId] = useState<string>();

  const upsertThread = useCallback((thread: ChatThreadSummary) => {
    setThreads((current) => [thread, ...current.filter((item) => item.id !== thread.id)]);
  }, []);

  const removeThread = useCallback((threadId: string) => {
    setThreads((current) => current.filter((thread) => thread.id !== threadId));
  }, []);

  const value = useMemo(() => ({
    threads,
    historyLoadState: initialLoadState,
    activeThreadId,
    setActiveThreadId,
    upsertThread,
    removeThread,
  }), [activeThreadId, initialLoadState, removeThread, threads, upsertThread]);

  return <ChatHistoryContext.Provider value={value}>{children}</ChatHistoryContext.Provider>;
}

export function useChatHistory() {
  const value = useContext(ChatHistoryContext);
  if (!value) throw new Error("useChatHistory must be used inside ChatHistoryProvider");
  return value;
}
