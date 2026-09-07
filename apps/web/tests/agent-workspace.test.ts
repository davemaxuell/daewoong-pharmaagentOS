import { expect, it } from "vitest";
import { parseReviewDraft } from "@/lib/agent-workspace";

const draft = { version: 1, objective: "Review retained evidence", template: "impact", updatedAt: "2026-09-07T00:00:00Z" };

it("restores a valid local brief without inventing an execution state", () => {
  expect(parseReviewDraft(JSON.stringify(draft))).toEqual(draft);
});

it("rejects corrupt, incompatible, and unbounded browser drafts", () => {
  for (const raw of [null, "{", "null", JSON.stringify({ ...draft, version: 2 }), JSON.stringify({ ...draft, objective: " " }), JSON.stringify({ ...draft, objective: "x".repeat(3001) }), JSON.stringify({ ...draft, template: "unknown" }), JSON.stringify({ ...draft, updatedAt: "not-a-date" })]) {
    expect(parseReviewDraft(raw)).toBeNull();
  }
});
