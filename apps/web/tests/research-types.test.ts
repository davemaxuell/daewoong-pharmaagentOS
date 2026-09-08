import { expect, it } from "vitest";
import { mergeResearchRun, researchText, type ResearchRun } from "@/lib/research-types";

const base: ResearchRun = {
  id: "run", objective: "Prepare an FDA brief", language: "en", status: "running", stage: "reading",
  revision: 1, created_at: "2026-09-08T12:00:00Z", updated_at: "2026-09-08T12:00:00Z",
  started_at: null, finished_at: null, model_calls: 1, max_model_calls: 12, error_code: null,
  can_resume: false, plan: [], sources: [], result: null,
  events: [{ sequence: 1, kind: "started", stage: "planning", data: {}, created_at: "2026-09-08T12:00:00Z" }],
};

it("does not let a late polling response undo Stop", () => {
  const stopped = { ...base, revision: 3, status: "stopped" as const };
  expect(mergeResearchRun(stopped, { ...base, revision: 2 })).toEqual(stopped);
});

it("keeps ordered, deduplicated activity when incremental responses overlap", () => {
  const next = { ...base, revision: 2, events: [...base.events, { ...base.events[0], sequence: 2, kind: "plan_saved" }] };
  expect(mergeResearchRun(mergeResearchRun(base, next), next).events.map((event) => event.sequence)).toEqual([1, 2]);
});

it("does not mix task history when switching tasks", () => {
  const other = { ...base, id: "other", events: [] };
  expect(mergeResearchRun(base, other).events).toEqual([]);
});

it("exports the cited draft and its review questions", () => {
  const output = researchText({ ...base, status: "completed", result: {
    title: "Review brief", findings: [{ statement: "An attributed finding", citation_ids: ["S1"] }],
    review_questions: ["What should we review?"], limitations: ["Public sources only"],
  } });
  expect(output).toContain("An attributed finding [S1]");
  expect(output).toContain("Draft for human review");
  expect(output).toContain("What should we review?");
});
