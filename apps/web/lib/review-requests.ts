import { parseReviewDraft, reviewTemplates } from "./agent-workspace";

export const REQUESTS_KEY = "pharmaagent-os:review-requests:v1";
export const MAX_REQUESTS = 30;
export type ReviewRequest = {
  id: string;
  template: string;
  objective: string;
  sourceUrl: string;
  updatedAt: string;
};

export function validFdaUrl(value: string): boolean {
  if (!value.trim()) return true;
  try {
    const url = new URL(value.trim());
    return (
      url.protocol === "https:" &&
      !url.username &&
      !url.password &&
      (url.hostname === "fda.gov" || url.hostname.endsWith(".fda.gov"))
    );
  } catch {
    return false;
  }
}

export function readRequests(
  raw: string | null,
  legacy: string | null = null,
): ReviewRequest[] {
  if (raw === null) {
    const old = parseReviewDraft(legacy);
    return old
      ? [
          {
            id: "legacy-review",
            template: old.template,
            objective: old.objective,
            sourceUrl: "",
            updatedAt: old.updatedAt,
          },
        ]
      : [];
  }
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed) || parsed.length > MAX_REQUESTS)
    throw new Error("Invalid request archive");
  const seen = new Set<string>();
  return parsed.map((item: unknown) => {
    if (!item || typeof item !== "object") throw new Error("Invalid request");
    const value = item as Partial<ReviewRequest>;
    if (
      typeof value.id !== "string" ||
      !value.id ||
      value.id.length > 100 ||
      seen.has(value.id) ||
      typeof value.objective !== "string" ||
      !value.objective.trim() ||
      value.objective.length > 3000 ||
      !reviewTemplates.some((template) => template.id === value.template) ||
      typeof value.sourceUrl !== "string" ||
      value.sourceUrl.length > 2000 ||
      !validFdaUrl(value.sourceUrl) ||
      typeof value.updatedAt !== "string" ||
      !Number.isFinite(Date.parse(value.updatedAt))
    )
      throw new Error("Invalid request");
    seen.add(value.id);
    return {
      id: value.id,
      template: value.template!,
      objective: value.objective,
      sourceUrl: value.sourceUrl,
      updatedAt: value.updatedAt,
    };
  });
}

export function requestText(request: ReviewRequest, korean: boolean): string {
  const template = reviewTemplates.find(
    (item) => item.id === request.template,
  )!;
  return korean
    ? `PharmaAgent OS — 검토 요청 초안\n상태: 초안 · AI 분석 및 제출 전\n\n검토 유형: ${template.ko}\n검토 질문:\n${request.objective}\n\nFDA 원문 링크: ${request.sourceUrl || "아직 추가하지 않음"}\n링크의 원문은 아직 가져오거나 검증하지 않았습니다.\n\n저장 시각: ${request.updatedAt}\n이 파일은 검토 요청서이며, 분석 결과나 승인된 보고서가 아닙니다.\n`
    : `PharmaAgent OS — Review request draft\nStatus: Draft · Not submitted or analyzed\n\nReview type: ${template.en}\nQuestion:\n${request.objective}\n\nFDA source link: ${request.sourceUrl || "Not added yet"}\nThe linked source has not been retrieved or verified.\n\nSaved at: ${request.updatedAt}\nThis is a review request, not an analysis result or an approved report.\n`;
}
