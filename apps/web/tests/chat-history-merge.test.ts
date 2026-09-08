import { expect, it } from "vitest";
import { mergeChatHistory } from "@/lib/chat-history-merge";
import type { ChatThreadSummary } from "@/lib/types";

function thread(id: string, updatedAt = "2026-09-08T00:00:00Z"): ChatThreadSummary {
  return { id, title: id, updatedAt, createdAt: updatedAt, lastMessageAt: updatedAt,
    activeLetterIds: [], modelPreference: "auto", retrievalPreference: "auto" };
}

it("keeps chats created while the sidebar request was in flight", () => {
  const created = thread("new", "2026-09-09T00:00:00Z");
  expect(mergeChatHistory([created], [thread("old")], new Set(["new"]))).toEqual([created, thread("old")]);
});

it("does not resurrect archived chats or replace a newer local revision", () => {
  const updated = { ...thread("updated"), title: "Latest title" };
  expect(mergeChatHistory([updated], [thread("archived"), thread("updated")], new Set(["archived", "updated"]))).toEqual([updated]);
});

it("accepts a fresh server snapshot for untouched chats", () => {
  expect(mergeChatHistory([thread("removed")], [thread("current")], new Set())).toEqual([thread("current")]);
});
