import { expect, it } from "vitest";
import { readRequests, requestText, validFdaUrl } from "@/lib/review-requests";

const request = {
  id: "one",
  template: "impact",
  objective: "Review the warning letter",
  sourceUrl: "https://www.fda.gov/example",
  updatedAt: "2026-09-08T00:00:00Z",
};

it("preserves a previous browser draft when introducing saved requests", () => {
  const old = JSON.stringify({ version: 1, ...request });
  expect(readRequests(null, old)[0]).toMatchObject({
    id: "legacy-review",
    objective: request.objective,
  });
  expect(readRequests("[]", old)).toEqual([]);
});

it("refuses corrupt archives instead of silently replacing existing work", () => {
  for (const raw of [
    "null",
    "{",
    JSON.stringify([request, request]),
    JSON.stringify([{ ...request, objective: " " }]),
    JSON.stringify([{ ...request, template: "unknown" }]),
  ]) {
    expect(() => readRequests(raw)).toThrow();
  }
});

it("accepts FDA HTTPS links and rejects misleading hosts and unsafe schemes", () => {
  expect(validFdaUrl("")).toBe(true);
  expect(validFdaUrl(request.sourceUrl)).toBe(true);
  for (const value of [
    "javascript:alert(1)",
    "https://fda.gov.example.com",
    "https://fda.gov@evil.test",
    "http://fda.gov",
  ])
    expect(validFdaUrl(value)).toBe(false);
});

it("exports a readable request without representing it as an executed review", () => {
  expect(requestText(request, false)).toContain("Not submitted or analyzed");
  expect(requestText(request, true)).toContain("AI 분석 및 제출 전");
  expect(requestText(request, false)).toContain(request.objective);
});
