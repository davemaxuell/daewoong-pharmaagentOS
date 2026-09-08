import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { ChatWorkspace } from "@/components/chat-workspace";
import type { ChatThread } from "@/lib/types";

vi.stubGlobal("React", React);
vi.mock("next/navigation", () => ({ useRouter: () => ({}) }));
vi.mock("@/app/(portal)/ask/actions", () => ({}));
vi.mock("@/components/chat-history-context", () => ({ useChatHistory: () => ({}) }));
vi.mock("@/lib/i18n", () => ({ useI18n: () => ({ locale: "en", text: (en: string) => en }) }));

function renderAnswer(generationUsed: boolean, sourceCount = 1) {
  const stamp = "2026-09-08T00:00:00Z";
  const thread: ChatThread = {
    id: "test-conversation", title: "Test question", modelPreference: "auto",
    retrievalPreference: "auto", activeLetterIds: [], lastMessageAt: stamp,
    createdAt: stamp, updatedAt: stamp,
    messages: [
      { id: "question", sequence: 1, role: "user", content: "Explain this evidence", status: "complete", citations: [], generationUsed: false, createdAt: stamp },
      { id: "answer", sequence: 2, role: "assistant", content: "Retained source content [1]", status: "complete", createdAt: stamp,
        generationUsed, attemptedModelId: "test-model", effectiveModelId: generationUsed ? "test-model" : undefined,
        retrievalStrategy: "corpus", citations: sourceCount ? [{ id: "source", letterId: "letter", company: "Test fixture", title: "Test evidence", issueDate: stamp, postedDate: stamp, documentType: "Warning letter", anchor: "p1", excerpt: "Retained source content", sourceUrl: "https://www.fda.gov/", score: 1 }] : [] },
    ],
  };
  return renderToStaticMarkup(React.createElement(ChatWorkspace, { letters: [], initialThread: thread }));
}

it("explains a failed AI response and preserves source excerpts inside a closed disclosure", () => {
  const html = renderAnswer(false);
  expect(html).toContain("could not finish the AI explanation");
  expect(html).toMatch(/<details><summary>Read the original source excerpts<\/summary>[\s\S]*Retained source content/);
  expect(html).not.toContain("<details open");
  expect(html).toContain("Sources (1)");
});

it("keeps a successful AI answer directly readable", () => {
  const html = renderAnswer(true);
  expect(html).toContain("Retained source content");
  expect(html).not.toContain("chat-fallback-guide");
});

it("does not claim sources were found when there are none", () => {
  const html = renderAnswer(false, 0);
  expect(html).not.toContain("We found sources");
  expect(html).toContain("No matching sources");
});
