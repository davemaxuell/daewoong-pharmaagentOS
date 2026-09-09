import "server-only";
import { backendOrigin } from "@/lib/backend-origin";

import {
  seedAdmin,
  seedChanges,
  seedDashboard,
  seedLetters,
  seedReviewItems,
  seedSavedViews,
} from "@/lib/seed-data";
import { getBackendBearerAssertion } from "@/lib/backend-auth";
import { normalizeRagAnswer } from "@/lib/rag-contract";
import type {
  AdminData,
  ApiResult,
  ChangeEvent,
  ChatMessage,
  ChatModelProfile,
  ChatRetrievalMode,
  ChatRetrievalStrategy,
  ChatThread,
  ChatThreadPage,
  ChatThreadSummary,
  DashboardData,
  Evidence,
  Finding,
  HealthCheck,
  Letter,
  LetterAiArtifact,
  LetterAiArtifactLanguage,
  LetterAiArtifactType,
  LifecycleEvent,
  RagAnswer,
  RagCitation,
  RagConversationMessage,
  RagFilter,
  RagQueryOptions,
  ReviewItem,
  ReviewState,
  SavedView,
  SavedViewCriteria,
  TrendPoint,
} from "@/lib/types";

type UnknownRecord = Record<string, unknown>;

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly requestId?: string,
  ) {
    super(`API request failed with status ${status}`);
    this.name = "ApiRequestError";
  }
}

const API_BASE_URL = backendOrigin();

function isLocalApi(url: string) {
  try {
    return ["localhost", "127.0.0.1", "::1"].includes(new URL(url).hostname);
  } catch {
    return false;
  }
}

function asRecord(value: unknown): UnknownRecord | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : undefined;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function asStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === "string");
}

function first(record: UnknownRecord, ...keys: string[]): unknown {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null) return record[key];
  }
  return undefined;
}

function unwrapList(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload;
  const record = asRecord(payload);
  if (!record) return [];
  for (const key of ["items", "results", "data", "letters", "events"]) {
    const candidate = record[key];
    if (Array.isArray(candidate)) return candidate;
    const nested = asRecord(candidate);
    if (nested) {
      const nestedList = unwrapList(nested);
      if (nestedList.length) return nestedList;
    }
  }
  return [];
}

function unwrapOne(payload: unknown): UnknownRecord | undefined {
  const record = asRecord(payload);
  if (!record) return undefined;
  const nested = asRecord(record.data) ?? asRecord(record.result) ?? asRecord(record.letter);
  return nested ?? record;
}

const CHAT_MODEL_PROFILES = new Set<ChatModelProfile>(["auto", "fast", "balanced", "deep"]);
const CHAT_RETRIEVAL_MODES = new Set<ChatRetrievalMode>([
  "auto",
  "none",
  "metadata",
  "letter",
  "corpus",
]);
const CHAT_RETRIEVAL_STRATEGIES = new Set<ChatRetrievalStrategy>([
  "none",
  "metadata",
  "letter",
  "multi_letter",
  "corpus",
]);

function normalizeChatModelProfile(value: unknown, fallback: ChatModelProfile = "auto") {
  const profile = asString(value) as ChatModelProfile;
  return CHAT_MODEL_PROFILES.has(profile) ? profile : fallback;
}

function normalizeChatRetrievalMode(value: unknown, fallback: ChatRetrievalMode = "auto") {
  const mode = asString(value) as ChatRetrievalMode;
  return CHAT_RETRIEVAL_MODES.has(mode) ? mode : fallback;
}

function normalizeChatRetrievalStrategy(
  value: unknown,
  fallback: ChatRetrievalStrategy = "corpus",
) {
  const strategy = asString(value) as ChatRetrievalStrategy;
  return CHAT_RETRIEVAL_STRATEGIES.has(strategy) ? strategy : fallback;
}

function normalizeRagFilter(value: unknown): RagFilter {
  const record = asRecord(value) ?? {};
  return {
    letterId: asString(first(record, "letter_id", "letterId")) || undefined,
    company: asString(record.company) || undefined,
    category: asString(record.category) || undefined,
    regulation: asString(record.regulation) || undefined,
    subtype: asString(first(record, "drug_subtype", "subtype")) || undefined,
    issuingOffice: asString(first(record, "issuing_office", "issuingOffice")) || undefined,
    dateFrom: asString(first(record, "issue_date_from", "dateFrom")) || undefined,
    dateTo: asString(first(record, "issue_date_to", "dateTo")) || undefined,
    postedFrom: asString(first(record, "posted_from", "postedFrom")) || undefined,
    postedTo: asString(first(record, "posted_to", "postedTo")) || undefined,
  };
}

function normalizeRagCitation(value: unknown, index: number): RagCitation | undefined {
  const citation = asRecord(value);
  if (!citation) return undefined;
  const letterId = asString(first(citation, "warning_letter_id", "letter_id", "letterId"));
  const excerpt = asString(citation.excerpt);
  if (!letterId || !excerpt) return undefined;
  return {
    id: asString(first(citation, "chunk_id", "id"), `citation-${index + 1}`),
    letterId,
    company: asString(first(citation, "company_name", "company"), "FDA Drug letter"),
    title: asString(citation.title, "Official FDA source evidence"),
    issueDate: asString(first(citation, "issue_date", "issueDate")),
    postedDate: asString(first(citation, "posted_date", "postedDate")),
    documentType: asString(first(citation, "document_type", "documentType"), "Warning letter"),
    anchor: asString(first(citation, "source_anchor", "anchor"), "source"),
    excerpt,
    sourceUrl: asString(first(citation, "source_url", "sourceUrl"), "https://www.fda.gov/"),
    score: asNumber(citation.score),
    documentVersionId: asString(
      first(citation, "document_version_id", "documentVersionId"),
    ) || undefined,
    sourceVersion: asString(first(citation, "source_version", "sourceVersion")) || undefined,
    sourceHash: asString(first(citation, "source_hash", "sourceHash")) || undefined,
  };
}

async function requestApi(path: string, init?: RequestInit): Promise<unknown> {
  if (!API_BASE_URL) throw new Error("API_BASE_URL is not configured");

  const token = await getBackendBearerAssertion();
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!token && isLocalApi(API_BASE_URL)) {
    headers.set("X-Dev-User", process.env.API_DEV_USER ?? "portal-dev");
    headers.set(
      "X-Dev-Roles",
      process.env.API_DEV_ROLES ?? process.env.APP_DEMO_ROLES ?? "viewer",
    );
  } else if (!token) {
    throw new Error("An authenticated server session is required for the configured API origin");
  }

  const timeoutSignal = AbortSignal.timeout(
    path === "/api/v1/rag/query"
      ? 50_000
      : path.includes("/ai-artifacts/")
        ? 360_000
        // Hosted cold starts and managed-database connections can exceed 3.5 seconds.
        : 15_000,
  );
  const signal = init?.signal
    ? AbortSignal.any([init.signal, timeoutSignal])
    : timeoutSignal;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    // Grounded generation may include an upstream model call after retrieval. A caller signal
    // is combined with the bounded timeout so a stopped browser request closes the upstream
    // connection instead of merely hiding a still-running fetch in the UI.
    signal,
  });

  if (!response.ok) {
    let requestId: string | undefined;
    try {
      const problem = asRecord(await response.json());
      requestId = asString(first(problem ?? {}, "request_id", "requestId")) || undefined;
    } catch {
      // Upstream failures are intentionally reduced to status and optional correlation ID.
    }
    throw new ApiRequestError(response.status, requestId);
  }

  if (response.status === 204) return null;
  return response.json() as Promise<unknown>;
}

function normalizeReviewState(value: unknown): ReviewState {
  const state = asString(value).toLowerCase();
  if (["pending", "auto_approved", "approved", "needs_revision", "rejected"].includes(state)) {
    return state as ReviewState;
  }
  return "pending";
}

function normalizeLetterAnalysisState(value: unknown): Letter["reviewState"] {
  const state = asString(value).toLowerCase();
  if (!state) return "not_generated";
  if (["pending", "auto_approved", "approved", "needs_revision", "rejected"].includes(state)) {
    return state as Letter["reviewState"];
  }
  return "not_generated";
}

const LIFECYCLE_STATES = new Set<Letter["lifecycleState"]>([
  "ACTIVE",
  "NEW",
  "UPDATED",
  "RESPONSE_ADDED",
  "CLOSEOUT_ADDED",
  "RESTORED",
]);

function normalizeLifecycleState(
  value: unknown,
  lifecycle: LifecycleEvent[],
  hasResponse: boolean,
  hasCloseout: boolean,
): Letter["lifecycleState"] {
  const explicit = asString(value).toUpperCase() as Letter["lifecycleState"];
  if (LIFECYCLE_STATES.has(explicit)) return explicit;
  const latest = lifecycle.find((event) => LIFECYCLE_STATES.has(event.type as Letter["lifecycleState"]));
  if (latest) return latest.type as Letter["lifecycleState"];
  if (hasCloseout) return "CLOSEOUT_ADDED";
  if (hasResponse) return "RESPONSE_ADDED";
  return "ACTIVE";
}

function normalizeEvidence(value: unknown): Evidence | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const anchor = asString(first(record, "anchor", "source_anchor", "sourceAnchor"));
  const excerpt = asString(record.excerpt);
  if (!anchor || !excerpt) return undefined;
  return {
    anchor,
    excerpt,
    section: asString(first(record, "section", "section_path", "sectionPath"), "Source section"),
  };
}

function normalizeFinding(value: unknown, index: number): Finding | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const evidence = unwrapList(first(record, "evidence", "anchors"))
    .map(normalizeEvidence)
    .filter((entry): entry is Evidence => Boolean(entry));
  return {
    id: asString(record.id, `finding-${index + 1}`),
    label: asString(record.label, String(index + 1).padStart(2, "0")),
    title: asString(first(record, "title", "category", "finding_title"), `Finding ${index + 1}`),
    finding: asString(first(record, "finding", "summary", "text"), "Source-backed finding available in the API record."),
    categories: asStrings(record.categories),
    processLenses: asStrings(first(record, "process_lenses", "processLenses")).filter(
      (item): item is Finding["processLenses"][number] =>
        ["Preventive", "Monitoring", "Retrospective"].includes(item),
    ),
    regulatoryReferences: asStrings(first(record, "regulatory_references", "regulatoryReferences")),
    evidence,
    requestedActions: asStrings(first(record, "fda_requested_actions", "requestedActions")),
    comparisonQuestions: asStrings(first(record, "comparison_points", "comparisonQuestions")),
    attentionLevel: ["high", "medium", "routine"].includes(asString(first(record, "attention_level", "attentionLevel")))
      ? (asString(first(record, "attention_level", "attentionLevel")) as Finding["attentionLevel"])
      : "routine",
    confidence: asNumber(record.confidence, 0),
    reviewState: normalizeReviewState(first(record, "review_state", "reviewState")),
  };
}

function normalizeLifecycleEvent(value: unknown, index: number): LifecycleEvent | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const rawType = asString(first(record, "event_type", "type"), "UPDATED");
  return {
    id: asString(record.id, `event-${index}`),
    type: rawType as LifecycleEvent["type"],
    at: asString(first(record, "occurred_at", "detected_at", "at")),
    title: asString(record.title, rawType.replaceAll("_", " ")),
    detail:
      asString(first(record, "detail", "summary", "description")) ||
      "A source or lifecycle state change was recorded without overwriting prior evidence.",
    version: asString(first(record, "version", "source_version", "source_version_id")) || undefined,
  };
}

function normalizeOriginalSections(
  markdownValue: unknown,
  anchorsValue: unknown,
  highlightedAnchors: Set<string>,
): Letter["originalSections"] {
  const anchorRows = unwrapList(anchorsValue)
    .map(asRecord)
    .filter((entry): entry is UnknownRecord => Boolean(entry));
  if (anchorRows.length) {
    const sections: Letter["originalSections"] = [];
    let current: Letter["originalSections"][number] | undefined;
    anchorRows.forEach((row, index) => {
      const anchor = asString(first(row, "anchor", "id"), `source-${index + 1}`);
      const text = asString(first(row, "text", "content"));
      const display = asString(first(row, "display", "formatted", "display_text"), text);
      const kind = asString(first(row, "kind", "type"), "paragraph");
      if (!text) return;
      if (kind === "heading" || !current) {
        if (current) sections.push(current);
        current = {
          anchor,
          heading: kind === "heading" ? text : "Official FDA source",
          paragraphs: kind === "heading" ? [] : [display],
          highlighted: highlightedAnchors.has(anchor),
        };
      } else {
        current.paragraphs.push(display);
        current.highlighted ||= highlightedAnchors.has(anchor);
      }
    });
    if (current) sections.push(current);
    return sections;
  }

  const markdown = asString(markdownValue);
  if (!markdown) return [];
  const sections: Letter["originalSections"] = [];
  let current: Letter["originalSections"][number] | undefined;
  markdown.split(/\n{2,}/).forEach((block, index) => {
    const trimmed = block.trim();
    if (!trimmed) return;
    const heading = trimmed.match(/^#{1,6}\s+(.+)$/m);
    if (heading) {
      if (current) sections.push(current);
      current = {
        anchor: `normalized-section-${sections.length + 1}`,
        heading: heading[1].trim(),
        paragraphs: [],
      };
      const remainder = trimmed.replace(heading[0], "").trim();
      if (remainder) current.paragraphs.push(remainder);
    } else {
      current ??= { anchor: `normalized-section-${index + 1}`, heading: "Official FDA source", paragraphs: [] };
      current.paragraphs.push(trimmed.replace(/^[-*]\s+/gm, ""));
    }
  });
  if (current) sections.push(current);
  return sections;
}

function normalizeLetterAiArtifact(value: unknown): LetterAiArtifact | undefined {
  const record = asRecord(value);
  const content = asRecord(record?.content);
  if (!record || !content) return undefined;
  const artifactType = asString(first(record, "artifact_type", "artifactType"));
  if (!["translation", "findings", "summary"].includes(artifactType)) return undefined;
  const language = asString(record.language);
  if (!["en", "ko"].includes(language)) return undefined;

  const sections = unwrapList(content.sections)
    .map((value) => {
      const section = asRecord(value);
      if (!section) return undefined;
      const anchor = asString(section.anchor);
      const heading = asString(section.heading);
      if (!anchor || !heading) return undefined;
      return { anchor, heading, paragraphs: asStrings(section.paragraphs) };
    })
    .filter((value): value is NonNullable<typeof value> => Boolean(value));
  const artifactFindings = unwrapList(content.findings)
    .map((value) => {
      const finding = asRecord(value);
      if (!finding) return undefined;
      const title = asString(finding.title);
      const statement = asString(first(finding, "finding", "finding_text"));
      if (!title || !statement) return undefined;
      const attention = asString(first(finding, "attention_level", "attentionLevel"));
      return {
        label: asString(finding.label),
        title,
        finding: statement,
        requestedActions: asStrings(first(finding, "requested_actions", "requestedActions")),
        categories: asStrings(finding.categories),
        attentionLevel: (["high", "medium", "routine"].includes(attention)
          ? attention
          : "routine") as "high" | "medium" | "routine",
        evidenceAnchors: asStrings(first(finding, "evidence_anchors", "evidenceAnchors")),
      };
    })
    .filter((value): value is NonNullable<typeof value> => Boolean(value));
  const attentionPoints = unwrapList(first(content, "attention_points", "attentionPoints"))
    .map((value) => {
      const point = asRecord(value);
      if (!point) return undefined;
      const title = asString(point.title);
      const rationale = asString(point.rationale);
      if (!title || !rationale) return undefined;
      return {
        title,
        rationale,
        sourceAnchors: asStrings(first(point, "source_anchors", "sourceAnchors")),
      };
    })
    .filter((value): value is NonNullable<typeof value> => Boolean(value));

  return {
    id: asString(record.id),
    documentVersionId: asString(first(record, "document_version_id", "documentVersionId")),
    artifactType: artifactType as LetterAiArtifactType,
    language: language as LetterAiArtifactLanguage,
    content: {
      sections: sections.length ? sections : undefined,
      findings: artifactFindings.length ? artifactFindings : undefined,
      executiveSummary: asString(first(content, "executive_summary", "executiveSummary")) || undefined,
      attentionPoints: attentionPoints.length ? attentionPoints : undefined,
      comparisonQuestions: asStrings(first(content, "comparison_questions", "comparisonQuestions")),
      disclaimer: asString(content.disclaimer) || undefined,
    },
    provider: asString(record.provider),
    modelId: asString(first(record, "model_id", "modelId")),
    promptVersion: asString(first(record, "prompt_version", "promptVersion")),
    sourceHash: asString(first(record, "source_hash", "sourceHash")),
    createdAt: asString(first(record, "created_at", "createdAt")),
  };
}

function marcsCmsFromFdaUrl(sourceUrl: string): string {
  return sourceUrl.match(/-(\d{5,8})-\d{8}\/?(?:[?#].*)?$/)?.[1] ?? "";
}

function normalizeLetter(value: unknown): Letter | undefined {
  const record = asRecord(value);
  if (!record) return undefined;

  const id = asString(first(record, "id", "warning_letter_id", "letter_id"));
  const company = asString(first(record, "company", "company_name"));
  if (!id || !company) return undefined;

  const productClasses = asStrings(first(record, "product_classes", "normalized_product_classes", "productClasses"));
  const findings = unwrapList(first(record, "findings", "violations"))
    .map(normalizeFinding)
    .filter((entry): entry is Finding => Boolean(entry));
  const lifecycle = unwrapList(first(record, "lifecycle", "change_events", "events"))
    .map(normalizeLifecycleEvent)
    .filter((entry): entry is LifecycleEvent => Boolean(entry));
  const summary = asRecord(record.summary);
  const currentVersion = asRecord(first(record, "current_version", "currentVersion"));
  const documents = unwrapList(record.documents)
    .map(asRecord)
    .filter((entry): entry is UnknownRecord => Boolean(entry));
  const issuingOffices = asStrings(first(record, "issuing_offices", "issuingOffices"));
  const highlightedAnchors = new Set(findings.flatMap((finding) => finding.evidence.map((item) => item.anchor)));
  const originalSections = normalizeOriginalSections(
    first(record, "normalized_markdown", "normalizedMarkdown"),
    first(currentVersion ?? {}, "anchors", "source_anchors"),
    highlightedAnchors,
  );
  const aiArtifacts = unwrapList(first(record, "ai_artifacts", "aiArtifacts"))
    .map(normalizeLetterAiArtifact)
    .filter((entry): entry is LetterAiArtifact => Boolean(entry));
  const summaryReviewState = first(summary ?? {}, "review_state", "reviewState");
  const currentHash = first(currentVersion ?? {}, "canonical_hash", "raw_sha256", "source_hash", "content_hash");
  const currentVersionNumber = first(currentVersion ?? {}, "version_number", "version", "id");
  const linkedDocumentTypes = new Set(documents.map((document) => asString(first(document, "document_type", "documentType"))));
  const regulations = asStrings(record.regulations);
  const findingRegulations = findings.flatMap((finding) => finding.regulatoryReferences);
  const hasResponse =
    asBoolean(first(record, "has_response", "hasResponse")) || linkedDocumentTypes.has("response");
  const hasCloseout =
    asBoolean(first(record, "has_closeout", "hasCloseout")) || linkedDocumentTypes.has("closeout");
  const lifecycleState = normalizeLifecycleState(
    first(record, "lifecycle_status", "lifecycle_state", "lifecycleStatus", "lifecycleState"),
    lifecycle,
    hasResponse,
    hasCloseout,
  );
  const sourceUrl = asString(first(record, "source_url", "canonical_url", "sourceUrl"), "https://www.fda.gov/");
  const marcsCms =
    asString(first(record, "marcs_cms", "marcs_cms_number", "marcsCms")) ||
    marcsCmsFromFdaUrl(sourceUrl);

  return {
    id,
    marcsCms,
    company,
    country: asString(record.country, "Not specified"),
    subject: asString(record.subject, "FDA Drug warning letter"),
    issueDate: asString(first(record, "issue_date", "issueDate")),
    postedDate: asString(first(record, "posted_date", "postedDate")),
    issuingOffice:
      issuingOffices.join(" · ") || asString(first(record, "issuing_office", "issuingOffice"), "U.S. FDA"),
    productClasses: productClasses.length ? productClasses : ["Drugs"],
    drugSubtypes: asStrings(first(record, "drug_subtypes", "drugSubtypes")),
    categories: asStrings(record.categories),
    regulations: [...new Set([...regulations, ...findingRegulations])],
    hasResponse,
    hasCloseout,
    reviewState: normalizeLetterAnalysisState(
      first(record, "review_state", "reviewState", "review_status") ?? summaryReviewState,
    ),
    lifecycleState,
    scopeStatus: "IN_SCOPE_DRUGS",
    executiveSummary:
      asString(first(record, "executive_summary", "executiveSummary")) ||
      asString(first(summary ?? {}, "executive_summary", "executiveSummary")),
    sourceUrl,
    retrievedAt:
      asString(first(record, "retrieved_at", "retrievedAt")) ||
      asString(first(currentVersion ?? {}, "retrieved_at", "retrievedAt")),
    sourceHash: asString(first(record, "source_hash", "content_hash", "sourceHash") ?? currentHash, "Not supplied"),
    sourceVersion: currentVersionNumber !== undefined
      ? `v${asString(currentVersionNumber, String(currentVersionNumber))}`
      : asString(first(record, "source_version", "sourceVersion"), "current"),
    facilityType: asString(first(record, "facility_type", "facilityType"), "Drug facility"),
    findings,
    lifecycle,
    originalSections,
    aiArtifacts,
  };
}

function normalizeChange(value: unknown, index: number): ChangeEvent | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const rawType = asString(first(record, "event_type", "type"), "UPDATED");
  return {
    id: asString(record.id, `change-${index}`),
    letterId: asString(first(record, "letter_id", "warning_letter_id")),
    company: asString(first(record, "company", "company_name"), "FDA Drug letter"),
    eventType: rawType as ChangeEvent["eventType"],
    occurredAt: asString(first(record, "occurred_at", "detected_at", "created_at")),
    summary: asString(first(record, "summary", "detail", "description"), rawType.replaceAll("_", " ")),
  };
}

async function liveLetters(query = ""): Promise<Letter[]> {
  const payload = await requestApi(`/api/v1/letters${query}`);
  return unwrapList(payload).map(normalizeLetter).filter((entry): entry is Letter => Boolean(entry));
}

async function liveAllLetters(): Promise<Letter[]> {
  const letters: Letter[] = [];
  const seenLetterIds = new Set<string>();
  const seenCursors = new Set<string>();
  let cursor: string | undefined;

  for (let pageNumber = 0; pageNumber < 10; pageNumber += 1) {
    const params = new URLSearchParams({ limit: "1000" });
    if (cursor) params.set("cursor", cursor);
    else params.delete("cursor");

    const payload = await requestApi(`/api/v1/letters/catalog?${params.toString()}`);
    const page = unwrapList(payload)
      .map(normalizeLetter)
      .filter((entry): entry is Letter => Boolean(entry));
    page.forEach((letter) => {
      if (seenLetterIds.has(letter.id)) return;
      seenLetterIds.add(letter.id);
      letters.push(letter);
    });

    const record = asRecord(payload);
    if (!record || !asBoolean(first(record, "has_more", "hasMore"))) return letters;
    const nextCursor = asString(first(record, "next_cursor", "nextCursor"));
    if (!nextCursor || seenCursors.has(nextCursor)) {
      throw new Error("API letter pagination did not advance");
    }
    seenCursors.add(nextCursor);
    cursor = nextCursor;
  }

  throw new Error("API letter pagination exceeded the 10,000-record safety limit");
}

export async function getLetters(query?: string): Promise<ApiResult<Letter[]>> {
  if (!API_BASE_URL) {
    return {
      data: seedLetters,
      mode: "seeded",
      detail: "API_BASE_URL is not configured; showing the isolated local preview dataset.",
    };
  }
  const letters = query === undefined ? await liveAllLetters() : await liveLetters(query);
  return { data: letters, mode: "live" };
}

/**
 * Facets shown beside the grounded chat must never fall back to synthetic records.
 * The conversation can still render without facets and the RAG request itself fails closed.
 */
export async function getChatLetters(query?: string): Promise<ApiResult<Letter[]>> {
  try {
    return {
      data: query === undefined ? await liveAllLetters() : await liveLetters(query),
      mode: "live",
    };
  } catch (error) {
    return {
      data: [],
      mode: "seeded",
      detail: error instanceof Error ? error.message : "API unavailable",
    };
  }
}

export async function getChatLetter(id: string): Promise<ApiResult<Letter | undefined>> {
  try {
    const payload = await requestApi(`/api/v1/letters/${encodeURIComponent(id)}`);
    const letter = normalizeLetter(unwrapOne(payload));
    if (!letter) throw new Error("API letter could not be normalized");
    return { data: letter, mode: "live" };
  } catch (error) {
    return {
      data: undefined,
      mode: "seeded",
      detail: error instanceof Error ? error.message : "API unavailable",
    };
  }
}

function normalizeChatMessage(value: unknown, index: number): ChatMessage | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const id = asString(record.id);
  const role = asString(record.role);
  const content = asString(record.content);
  if (!id || !content || !["user", "assistant"].includes(role)) return undefined;

  const routeMetadata = asRecord(first(record, "route_metadata", "routeMetadata")) ?? {};
  const modelMetadata = asRecord(first(record, "model_metadata", "modelMetadata")) ?? {};
  const generationMetadata = asRecord(first(modelMetadata, "generation")) ?? {};
  const requestSnapshot = asRecord(
    first(routeMetadata, "request_snapshot", "requestSnapshot"),
  );
  const rawFiltersApplied = first(routeMetadata, "filters_applied", "filtersApplied")
    ?? first(record, "filters_applied", "filtersApplied")
    ?? (requestSnapshot ? first(requestSnapshot, "filters") : undefined);
  const requestLanguageValue = asString(
    requestSnapshot ? first(requestSnapshot, "language") : undefined,
  );
  const requestMaxSourcesValue = asNumber(
    requestSnapshot ? first(requestSnapshot, "max_sources", "maxSources") : undefined,
    0,
  );
  const requestRetrievalModeValue = requestSnapshot
    ? first(requestSnapshot, "retrieval_mode", "retrievalMode")
    : undefined;
  const requestModelProfileValue = requestSnapshot
    ? first(requestSnapshot, "model_profile", "modelProfile")
    : undefined;
  const rawStatus = asString(record.status, "complete");
  const statusValue = rawStatus === "completed"
    ? "complete"
    : rawStatus === "failed"
      ? "error"
      : rawStatus;
  const status = ["pending", "streaming", "complete", "error", "cancelled"].includes(statusValue)
    ? statusValue as ChatMessage["status"]
    : "complete";
  const requestedModelProfile = normalizeChatModelProfile(
    first(modelMetadata, "requested_model_profile", "requestedModelProfile", "requested_profile")
      ?? first(record, "requested_model_profile", "requestedModelProfile"),
  );
  const effectiveModelProfileValue = normalizeChatModelProfile(
    first(modelMetadata, "effective_model_profile", "effectiveModelProfile", "effective_profile")
      ?? first(record, "effective_model_profile", "effectiveModelProfile"),
  );
  const explicitEffectiveModelId = asString(
    first(modelMetadata, "effective_model_id", "effectiveModelId")
      ?? first(record, "effective_model_id", "effectiveModelId"),
  ) || undefined;
  const legacyGenerationModelId = asString(first(generationMetadata, "model_id", "modelId"))
    || undefined;
  const generationProvider = asString(generationMetadata.provider);
  const generationFallback = asString(generationMetadata.fallback);
  const rawGenerationUsed = first(modelMetadata, "generation_used", "generationUsed")
    ?? first(record, "generation_used", "generationUsed");
  const inferredGenerationUsed = Boolean(
    legacyGenerationModelId
      && generationProvider
      && generationProvider !== "deterministic-source-fallback"
      && !generationFallback,
  );
  const generationUsed = typeof rawGenerationUsed === "boolean"
    ? rawGenerationUsed
    : inferredGenerationUsed;
  const attemptedModelId = asString(
    first(modelMetadata, "attempted_model_id", "attemptedModelId")
      ?? first(record, "attempted_model_id", "attemptedModelId"),
  ) || (generationProvider !== "deterministic-source-fallback" ? legacyGenerationModelId : undefined);
  const effectiveModelId = explicitEffectiveModelId
    ?? (generationUsed ? legacyGenerationModelId : undefined);
  const evidenceValue = asString(
    first(routeMetadata, "evidence_sufficiency", "evidenceSufficiency")
      ?? first(record, "evidence_sufficiency", "evidenceSufficiency"),
  );
  const interpretationValue = asString(
    first(routeMetadata, "interpretation_label", "interpretationLabel")
      ?? first(record, "interpretation_label", "interpretationLabel"),
  );

  return {
    id,
    sequence: asNumber(first(record, "sequence", "sequence_no", "sequenceNo"), index + 1),
    role: role as ChatMessage["role"],
    content,
    status,
    clientMessageId: asString(first(record, "client_message_id", "clientMessageId")) || undefined,
    ragQueryId: asString(first(record, "rag_query_id", "ragQueryId")) || undefined,
    citations: unwrapList(record.citations)
      .map(normalizeRagCitation)
      .filter((citation): citation is RagCitation => Boolean(citation)),
    retrievalStrategy: normalizeChatRetrievalStrategy(
      first(routeMetadata, "retrieval_strategy", "retrievalStrategy")
        ?? first(record, "retrieval_strategy", "retrievalStrategy"),
      "none",
    ),
    routeReason: asString(
      first(routeMetadata, "route_reason", "routeReason")
        ?? first(record, "route_reason", "routeReason"),
    ) || undefined,
    requestedModelProfile,
    effectiveModelProfile: effectiveModelProfileValue === "auto"
      ? undefined
      : effectiveModelProfileValue,
    effectiveModelId,
    attemptedModelId,
    generationUsed,
    evidenceSufficiency: ["sufficient", "partial", "insufficient"].includes(evidenceValue)
      ? evidenceValue as ChatMessage["evidenceSufficiency"]
      : undefined,
    interpretationLabel: ["source_facts", "ai_synthesis", "internal_comparison"].includes(interpretationValue)
      ? interpretationValue as ChatMessage["interpretationLabel"]
      : undefined,
    filtersApplied: rawFiltersApplied === undefined
      ? undefined
      : normalizeRagFilter(rawFiltersApplied),
    requestLanguage: ["auto", "en", "ko"].includes(requestLanguageValue)
      ? requestLanguageValue as ChatMessage["requestLanguage"]
      : undefined,
    requestMaxSources: requestMaxSourcesValue >= 1 && requestMaxSourcesValue <= 10
      ? requestMaxSourcesValue
      : undefined,
    requestRetrievalMode: requestRetrievalModeValue === undefined
      ? undefined
      : normalizeChatRetrievalMode(requestRetrievalModeValue),
    requestModelProfile: requestModelProfileValue === undefined
      ? undefined
      : normalizeChatModelProfile(requestModelProfileValue),
    focusedDocumentVersionId: asString(
      first(routeMetadata, "focused_document_version_id", "focusedDocumentVersionId"),
    ) || undefined,
    createdAt: asString(first(record, "created_at", "createdAt")),
    updatedAt: asString(first(record, "updated_at", "updatedAt")) || undefined,
  };
}

function normalizeChatThreadSummary(value: unknown): ChatThreadSummary | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const id = asString(record.id);
  const title = asString(record.title).trim();
  if (!id || !title) return undefined;
  const createdAt = asString(first(record, "created_at", "createdAt"));
  const focusRecord = asRecord(record.focus);
  const focus = focusRecord
    ? {
        warningLetterId: asString(first(focusRecord, "warning_letter_id", "warningLetterId")),
        documentId: asString(first(focusRecord, "document_id", "documentId")),
        documentVersionId: asString(first(focusRecord, "document_version_id", "documentVersionId")),
        sourceChunkId: asString(first(focusRecord, "source_chunk_id", "sourceChunkId")),
        sourceMessageId: asString(first(focusRecord, "source_message_id", "sourceMessageId")),
        selectedAt: asString(first(focusRecord, "selected_at", "selectedAt")),
      }
    : undefined;
  return {
    id,
    title,
    modelPreference: normalizeChatModelProfile(first(record, "model_preference", "modelPreference")),
    retrievalPreference: normalizeChatRetrievalMode(
      first(record, "retrieval_preference", "retrievalPreference"),
    ),
    activeLetterIds: asStrings(first(record, "active_letter_ids", "activeLetterIds")),
    focus: focus?.warningLetterId && focus.documentVersionId && focus.sourceChunkId
      ? focus
      : undefined,
    archivedAt: asString(first(record, "archived_at", "archivedAt")) || undefined,
    lastMessageAt: asString(first(record, "last_message_at", "lastMessageAt"), createdAt),
    createdAt,
    updatedAt: asString(first(record, "updated_at", "updatedAt"), createdAt),
  };
}

function normalizeChatThread(value: unknown): ChatThread | undefined {
  const record = asRecord(value);
  const summary = normalizeChatThreadSummary(record);
  if (!record || !summary) return undefined;
  return {
    ...summary,
    messages: unwrapList(record.messages)
      .map(normalizeChatMessage)
      .filter((message): message is ChatMessage => Boolean(message))
      .sort((left, right) => left.sequence - right.sequence),
  };
}

export async function getChatThreads({
  page = 1,
  limit = 20,
  includeArchived = false,
  search,
}: {
  page?: number;
  limit?: number;
  includeArchived?: boolean;
  search?: string;
} = {}): Promise<ApiResult<ChatThreadPage>> {
  try {
    const params = new URLSearchParams({
      page: String(Math.max(1, Math.round(page))),
      limit: String(Math.min(100, Math.max(1, Math.round(limit)))),
      include_archived: String(includeArchived),
    });
    const normalizedSearch = search?.trim().slice(0, 200);
    if (normalizedSearch) params.set("q", normalizedSearch);
    const payload = await requestApi(`/api/v1/chat/threads?${params.toString()}`);
    const record = asRecord(payload) ?? {};
    const items = unwrapList(payload)
      .map(normalizeChatThreadSummary)
      .filter((thread): thread is ChatThreadSummary => Boolean(thread));
    return {
      mode: "live",
      data: {
        items,
        hasMore: asBoolean(first(record, "has_more", "hasMore")),
        nextCursor: asString(first(record, "next_cursor", "nextCursor")) || undefined,
        page: asNumber(record.page) || undefined,
        limit: asNumber(record.limit) || undefined,
        total: asNumber(record.total) || undefined,
      },
    };
  } catch (error) {
    return {
      mode: "seeded",
      data: { items: [], hasMore: false },
      detail: error instanceof Error ? error.message : "Chat history unavailable",
    };
  }
}

export async function getChatThread(id: string): Promise<ApiResult<ChatThread | undefined>> {
  try {
    const payload = await requestApi(`/api/v1/chat/threads/${encodeURIComponent(id)}`);
    const thread = normalizeChatThread(unwrapOne(payload));
    if (!thread) throw new Error("Chat thread could not be normalized");
    return { data: thread, mode: "live" };
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) {
      return { data: undefined, mode: "live" };
    }
    return {
      data: undefined,
      mode: "seeded",
      detail: error instanceof Error ? error.message : "Chat history unavailable",
    };
  }
}

export async function createChatThread(input: {
  title?: string;
  modelPreference?: ChatModelProfile;
  retrievalPreference?: ChatRetrievalMode;
  activeLetterIds?: string[];
} = {}): Promise<ChatThread> {
  const payload = await requestApi("/api/v1/chat/threads", {
    method: "POST",
    body: JSON.stringify({
      title: input.title,
      model_preference: input.modelPreference,
      retrieval_preference: input.retrievalPreference,
      active_letter_ids: input.activeLetterIds,
    }),
  });
  const thread = normalizeChatThread(unwrapOne(payload));
  if (!thread) throw new Error("API returned an invalid chat thread");
  return thread;
}

export async function updateChatThread(
  id: string,
  input: {
    title?: string;
    modelPreference?: ChatModelProfile;
    retrievalPreference?: ChatRetrievalMode;
    activeLetterIds?: string[];
  },
): Promise<ChatThreadSummary> {
  const payload = await requestApi(`/api/v1/chat/threads/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({
      title: input.title,
      model_preference: input.modelPreference,
      retrieval_preference: input.retrievalPreference,
      active_letter_ids: input.activeLetterIds,
    }),
  });
  const thread = normalizeChatThreadSummary(unwrapOne(payload));
  if (!thread) throw new Error("API returned an invalid chat thread update");
  return thread;
}

export async function archiveChatThread(id: string): Promise<void> {
  await requestApi(`/api/v1/chat/threads/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function focusChatThreadOnCitation(
  id: string,
  input: { assistantMessageId: string; chunkId: string },
): Promise<ChatThread> {
  const payload = await requestApi(`/api/v1/chat/threads/${encodeURIComponent(id)}/focus`, {
    method: "PUT",
    body: JSON.stringify({
      assistant_message_id: input.assistantMessageId,
      chunk_id: input.chunkId,
    }),
  });
  const thread = normalizeChatThread(unwrapOne(payload));
  if (!thread) throw new Error("API returned an invalid focused chat thread");
  return thread;
}

export async function clearChatThreadFocus(id: string): Promise<ChatThread> {
  const payload = await requestApi(`/api/v1/chat/threads/${encodeURIComponent(id)}/focus`, {
    method: "DELETE",
  });
  const thread = normalizeChatThread(unwrapOne(payload));
  if (!thread) throw new Error("API returned an invalid cleared chat thread");
  return thread;
}

export async function cancelPendingChatMessage(
  threadId: string,
  clientMessageId: string,
): Promise<ChatMessage> {
  const payload = await requestApi(
    `/api/v1/chat/threads/${encodeURIComponent(threadId)}/messages/${encodeURIComponent(clientMessageId)}/cancel`,
    { method: "POST" },
  );
  const message = normalizeChatMessage(unwrapOne(payload), 0);
  if (!message) throw new Error("API returned an invalid chat cancellation receipt");
  return message;
}

export async function getLetter(id: string): Promise<ApiResult<Letter | undefined>> {
  if (!API_BASE_URL) {
    return {
      data: seedLetters.find((letter) => letter.id === id),
      mode: "seeded",
      detail: "API_BASE_URL is not configured; showing the isolated local preview dataset.",
    };
  }
  const payload = await requestApi(`/api/v1/letters/${encodeURIComponent(id)}`);
  const letter = normalizeLetter(unwrapOne(payload));
  if (!letter) throw new Error("API letter could not be normalized");

  // The detail includes its exact current version and hash. A separate history
  // read adds latency and may select a newer response/closeout document instead.
  return { data: letter, mode: "live" };
}

export async function generateLetterAiArtifact(
  letterId: string,
  artifactType: LetterAiArtifactType,
  language: LetterAiArtifactLanguage,
): Promise<LetterAiArtifact> {
  const payload = await requestApi(
    `/api/v1/letters/${encodeURIComponent(letterId)}/ai-artifacts/${artifactType}?language=${language}`,
    { method: "POST" },
  );
  const artifact = normalizeLetterAiArtifact(unwrapOne(payload));
  if (!artifact) throw new Error("AI artifact response could not be validated");
  return artifact;
}

export async function getChanges(): Promise<ApiResult<ChangeEvent[]>> {
  if (!API_BASE_URL) {
    return {
      data: seedChanges,
      mode: "seeded",
      detail: "API_BASE_URL is not configured; showing the isolated local preview dataset.",
    };
  }
  const payload = await requestApi("/api/v1/changes?limit=20");
  const changes = unwrapList(payload)
    .map(normalizeChange)
    .filter((entry): entry is ChangeEvent => Boolean(entry));
  return { data: changes, mode: "live" };
}

export async function getNewLetterChanges(limit = 100): Promise<ApiResult<ChangeEvent[]>> {
  if (!API_BASE_URL) {
    return {
      data: seedChanges.filter((change) => change.eventType === "NEW"),
      mode: "seeded",
      detail: "API_BASE_URL is not configured; showing the isolated local preview dataset.",
    };
  }
  const boundedLimit = Math.min(100, Math.max(1, Math.round(limit)));
  const payload = await requestApi(`/api/v1/changes?event_type=NEW&limit=${boundedLimit}`);
  const changes = unwrapList(payload)
    .map(normalizeChange)
    .filter((entry): entry is ChangeEvent => Boolean(entry));
  return { data: changes, mode: "live" };
}

export async function getDashboard(): Promise<ApiResult<DashboardData>> {
  if (!API_BASE_URL) {
    return {
      data: seedDashboard,
      mode: "seeded",
      detail: "API_BASE_URL is not configured; showing the isolated local preview dataset.",
    };
  }

  const [changes, dashboardPayload] = await Promise.all([
    getChanges(),
    requestApi("/api/v1/dashboard"),
  ]);
  const dashboardRecord = unwrapOne(dashboardPayload);
  if (!dashboardRecord) throw new Error("Dashboard service returned an invalid response");
  const counts = asRecord(dashboardRecord?.counts);
  if (!counts) throw new Error("Dashboard service omitted its count report");
  const newCount = asNumber(counts.new_letters);
  const updatedCount = asNumber(counts.updated_letters);
  const responseCount = asNumber(counts.responses_added);
  const closeoutCount = asNumber(counts.closeouts_added);
  const reviewCount = asNumber(counts.pending_reviews);
  const totalCount = asNumber(counts.total_drug_letters);
  const categoryRows = Array.isArray(dashboardRecord.category_distribution)
    ? dashboardRecord.category_distribution
    : [];
  const categoryTrends = categoryRows
    .map((value) => {
      const row = asRecord(value);
      const label = asString(row?.category);
      return label ? { label, value: asNumber(row?.count) } : undefined;
    })
    .filter((item): item is TrendPoint => Boolean(item));
  return {
    mode: "live",
    data: {
      metrics: [
        { label: "New warning letters", value: String(newCount), delta: "Last 30 days", tone: "red", detail: "Reported by the connected FDA corpus service" },
        { label: "Updated warning letters", value: String(updatedCount), delta: "Last 30 days", tone: "ochre", detail: "Reported lifecycle changes" },
        { label: "Linked lifecycle documents", value: String(responseCount + closeoutCount), delta: `${responseCount} response · ${closeoutCount} closeout`, tone: "green", detail: "Reported in the last 30 days" },
        { label: "Open review items", value: String(reviewCount), delta: "Current", tone: "ink", detail: "Pending or needs-revision summaries" },
      ],
      changes: changes.data.slice(0, 8),
      categoryTrends,
      subtypeDistribution: [],
      regulations: [],
      health: [],
      discovery: {
        lastSuccess: asString(dashboardRecord.last_successful_discovery, "Not reported by API"),
        nextRun: "Not reported by API",
        recordsScanned: totalCount,
        inScope: totalCount,
        exceptions: asNumber(counts.scope_exceptions),
      },
    },
  };
}

export type ReviewQueueFilter = "open" | "high_attention" | "all";

export type ReviewQueueData = {
  items: ReviewItem[];
  nextCursor?: string;
  previousCursor?: string;
  total: number;
  page: number;
  pageSize: number;
};

export type ReviewReceipt = {
  reviewId: string;
  sourceSummaryId: string;
  resultingSummaryId: string;
  sourceDocumentVersionId: string;
  resultingRevision: number;
  state: ReviewState;
  reviewedBy: string;
  reviewedAt: string;
  contentChanged: boolean;
  requestId: string;
};

function seedCursorOffset(cursor?: string): number {
  if (!cursor?.startsWith("seed:")) return 0;
  const value = Number(cursor.slice(5));
  return Number.isSafeInteger(value) && value >= 0 ? value : 0;
}

export async function getReviewQueue(options: {
  view?: ReviewQueueFilter;
  cursor?: string;
  pageSize?: number;
} = {}): Promise<ApiResult<ReviewQueueData>> {
  const view = options.view ?? "open";
  const pageSize = Math.min(Math.max(options.pageSize ?? 10, 1), 100);
  if (!API_BASE_URL) {
    const filtered = seedReviewItems.filter((item) => {
      if (view === "all") return true;
      if (view === "high_attention") {
        return item.failedChecks.length > 0 || item.priority === "high";
      }
      return ["pending", "needs_revision"].includes(item.state);
    });
    const offset = seedCursorOffset(options.cursor);
    const items = filtered.slice(offset, offset + pageSize).map((item) => ({
      ...item,
      summaryRevision: item.summaryRevision ?? 1,
      documentVersionId: item.documentVersionId ?? item.summaryId,
      confidence: Number.isFinite(item.confidence) ? item.confidence : null,
      highAttention: item.failedChecks.length > 0 || item.priority === "high",
      relatedOpenItems: item.relatedOpenItems ?? 1,
    }));
    return {
      data: {
        items,
        nextCursor: offset + pageSize < filtered.length ? `seed:${offset + pageSize}` : undefined,
        previousCursor: offset > 0 ? `seed:${Math.max(0, offset - pageSize)}` : undefined,
        total: filtered.length,
        page: Math.floor(offset / pageSize) + 1,
        pageSize,
      },
      mode: "seeded",
      detail: "API_BASE_URL is not configured; showing the local preview dataset.",
    };
  }
  try {
    const query = new URLSearchParams({ view, page_size: String(pageSize) });
    if (options.cursor) query.set("cursor", options.cursor);
    const payload = await requestApi(`/api/v1/reviews?${query.toString()}`);
    const pageRecord = asRecord(payload);
    const items = unwrapList(payload)
      .map((value): ReviewItem | undefined => {
        const record = asRecord(value);
        const summary = asRecord(record?.summary);
        if (!record || !summary) return undefined;
        const validation = asRecord(summary.validation_report);
        const failedChecks = asStrings(record.failed_checks);
        const summaryId = asString(summary.id);
        const letterId = asString(record.warning_letter_id);
        if (!summaryId || !letterId) return undefined;
        return {
          id: `review-${summaryId}`,
          summaryId,
          summaryRevision: asNumber(summary.revision, 1),
          documentVersionId: asString(summary.document_version_id),
          letterId,
          company: asString(record.company_name, "FDA Drug letter"),
          marcsCms: asString(first(record, "marcs_cms_number", "marcs_cms"), letterId.slice(0, 8)),
          submittedAt: asString(first(summary, "created_at", "submitted_at")),
          priority: failedChecks.length > 1 ? "high" : "normal",
          trigger: failedChecks[0] ?? "Human approval is required by the active review policy",
          failedChecks,
          sourceExcerpt: asString(
            first(validation ?? {}, "source_excerpt", "evidence_excerpt"),
            "Open the immutable source dossier and verify every material statement against its anchored evidence.",
          ),
          aiFinding: asString(summary.executive_summary, "No derived summary was returned."),
          sourceAnchor: asString(first(validation ?? {}, "source_anchor", "anchor"), "source-dossier"),
          categories: asStrings(first(validation ?? {}, "categories", "taxonomy_labels")),
          confidence: typeof record.confidence === "number"
            ? record.confidence
            : typeof first(validation ?? {}, "confidence", "overall_confidence") === "number"
              ? asNumber(first(validation ?? {}, "confidence", "overall_confidence"))
              : null,
          highAttention: asBoolean(record.high_attention, failedChecks.length > 0),
          relatedOpenItems: asNumber(record.related_open_items, 1),
          state: normalizeReviewState(summary.review_state),
        };
      })
      .filter((item): item is ReviewItem => Boolean(item));
    return {
      data: {
        items,
        nextCursor: asString(pageRecord?.next_cursor) || undefined,
        previousCursor: asString(pageRecord?.previous_cursor) || undefined,
        total: asNumber(pageRecord?.total, items.length),
        page: asNumber(pageRecord?.page, 1),
        pageSize: asNumber(pageRecord?.page_size, pageSize),
      },
      mode: "live",
    };
  } catch (error) {
    throw error instanceof Error ? error : new Error("Review service unavailable");
  }
}

export async function getReviewItems(): Promise<ApiResult<ReviewItem[]>> {
  const result = await getReviewQueue({ view: "open", pageSize: 50 });
  return { ...result, data: result.data.items };
}

const SAVED_VIEW_ALERT_STATES = new Set<SavedView["alertState"]>([
  "off",
  "ready",
  "delivery_unavailable",
  "digest_scheduler_unavailable",
]);

function normalizeSavedViewCriteria(value: unknown): SavedViewCriteria {
  const record = asRecord(value) ?? {};
  const lifecycle = asString(first(record, "lifecycle_state", "lifecycle"));
  const review = asString(first(record, "review_state", "review"));
  const document = asString(first(record, "linked_document", "document"));
  return {
    query: asString(first(record, "query", "q")) || undefined,
    subtype: asString(first(record, "drug_subtype", "subtype")) || undefined,
    category: asString(record.category) || undefined,
    country: asString(record.country) || undefined,
    lifecycle: ["ACTIVE", "NEW", "UPDATED", "RESPONSE_ADDED", "CLOSEOUT_ADDED", "RESTORED"].includes(lifecycle)
      ? (lifecycle as SavedViewCriteria["lifecycle"])
      : undefined,
    review: ["auto_approved", "approved", "needs_revision", "rejected"].includes(review)
      ? (review as SavedViewCriteria["review"])
      : undefined,
    document: ["response", "closeout", "open"].includes(document)
      ? (document as SavedViewCriteria["document"])
      : undefined,
    postedFrom: asString(first(record, "posted_from", "postedFrom")) || undefined,
    postedTo: asString(first(record, "posted_to", "postedTo")) || undefined,
  };
}

function savedViewCriteriaPayload(criteria: SavedViewCriteria) {
  return {
    query: criteria.query || undefined,
    drug_subtype: criteria.subtype || undefined,
    category: criteria.category || undefined,
    country: criteria.country || undefined,
    lifecycle_state: criteria.lifecycle || undefined,
    review_state: criteria.review || undefined,
    linked_document: criteria.document || undefined,
    posted_from: criteria.postedFrom || undefined,
    posted_to: criteria.postedTo || undefined,
  };
}

function savedViewFilterLabels(criteria: SavedViewCriteria) {
  const fields: Array<[string, string | undefined]> = [
    ["Search", criteria.query],
    ["Drug subtype", criteria.subtype],
    ["Category", criteria.category],
    ["Country", criteria.country],
    ["Lifecycle", criteria.lifecycle],
    ["Review state", criteria.review],
    ["Linked documents", criteria.document],
    ["Posted from", criteria.postedFrom],
    ["Posted to", criteria.postedTo],
  ];
  const labels = fields.filter((entry): entry is [string, string] => Boolean(entry[1])).map(
    ([label, value]) => `${label}: ${value}`,
  );
  return labels.length ? labels : ["All active Drug letters"];
}

function normalizeSavedView(value: unknown): SavedView | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const id = asString(record.id);
  if (!id) return undefined;
  const criteria = normalizeSavedViewCriteria(record.criteria);
  const frequency = asString(first(record, "frequency", "cadence"), "immediate");
  const cadenceLabel = frequency.charAt(0).toUpperCase() + frequency.slice(1).toLowerCase();
  const cadence = asBoolean(record.active, true) && ["Immediate", "Daily", "Weekly"].includes(cadenceLabel)
    ? (cadenceLabel as SavedView["cadence"])
    : "Off";
  const alertStateValue = asString(first(record, "alert_state", "alertState"));
  const alertState = SAVED_VIEW_ALERT_STATES.has(alertStateValue as SavedView["alertState"])
    ? (alertStateValue as SavedView["alertState"])
    : "delivery_unavailable";
  const openUrl = asString(first(record, "open_url", "openUrl"));
  return {
    id,
    name: asString(record.name, "Saved Drug view"),
    description: asString(
      record.description,
      "Controlled filters for the admitted FDA Product: Drugs corpus.",
    ),
    criteria,
    filters: savedViewFilterLabels(criteria),
    cadence,
    alertState,
    resultCount: asNumber(first(record, "result_count", "resultCount"), 0),
    lastMatched: asString(first(record, "last_matched", "lastMatched"), "No matches yet"),
    owner: "You",
    openUrl: openUrl.startsWith("/drug-letters") ? openUrl : "/drug-letters",
    updatedAt: asString(first(record, "updated_at", "updatedAt")),
  };
}

export async function getSavedViews(): Promise<ApiResult<SavedView[]>> {
  if (!API_BASE_URL) {
    return {
      data: seedSavedViews,
      mode: "seeded",
      detail: "API_BASE_URL is not configured; showing the isolated local preview dataset.",
    };
  }
  const payload = await requestApi("/api/v1/saved-views?limit=100");
  const views = unwrapList(payload)
    .map(normalizeSavedView)
    .filter((view): view is SavedView => Boolean(view));
  return { data: views, mode: "live" };
}

export type SavedViewMutationInput = {
  name: string;
  description: string;
  criteria: SavedViewCriteria;
  cadence: SavedView["cadence"];
};

function savedViewMutationPayload(input: SavedViewMutationInput) {
  return {
    name: input.name,
    description: input.description,
    criteria: savedViewCriteriaPayload(input.criteria),
    cadence: input.cadence.toLowerCase(),
  };
}

export async function createSavedView(input: SavedViewMutationInput): Promise<SavedView> {
  const payload = await requestApi("/api/v1/saved-views", {
    method: "POST",
    body: JSON.stringify(savedViewMutationPayload(input)),
  });
  const view = normalizeSavedView(payload);
  if (!view) throw new Error("API returned an invalid saved-view confirmation");
  return view;
}

export async function updateSavedView(
  id: string,
  input: Partial<SavedViewMutationInput>,
): Promise<SavedView> {
  const body = {
    ...(input.name === undefined ? {} : { name: input.name }),
    ...(input.description === undefined ? {} : { description: input.description }),
    ...(input.criteria === undefined ? {} : { criteria: savedViewCriteriaPayload(input.criteria) }),
    ...(input.cadence === undefined ? {} : { cadence: input.cadence.toLowerCase() }),
  };
  const payload = await requestApi(`/api/v1/saved-views/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  const view = normalizeSavedView(payload);
  if (!view) throw new Error("API returned an invalid saved-view update confirmation");
  return view;
}

export async function deleteSavedView(id: string): Promise<void> {
  await requestApi(`/api/v1/saved-views/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function getAdminData(): Promise<ApiResult<AdminData>> {
  if (!API_BASE_URL) {
    return {
      data: seedAdmin,
      mode: "seeded",
      detail: "API_BASE_URL is not configured; showing the local preview dataset.",
    };
  }
  try {
    const [runsPayload, runtimePayload, notificationPayload] = await Promise.all([
      requestApi("/api/v1/admin/ingestion-runs?limit=10"),
      requestApi("/api/v1/admin/runtime-configuration"),
      requestApi("/api/v1/admin/notification-settings"),
    ]);
    const runtime = unwrapOne(runtimePayload);
    const notification = unwrapOne(notificationPayload);
    if (!runtime || !notification) {
      throw new Error("Administration service returned an incomplete runtime report");
    }
    const runs = unwrapList(runsPayload)
      .map(asRecord)
      .filter((run): run is UnknownRecord => Boolean(run));
    const modelId = asString(runtime.ai_model_id, "not configured");
    const promptVersion = asString(runtime.ai_prompt_version, "not configured");
    const aiConfigured = asBoolean(runtime?.ai_configured);
    const embeddingEnabled = asBoolean(runtime.embedding_enabled);
    const embeddingModelId = asString(runtime.embedding_model_id, "not configured");
    const embeddingDimensions = asNumber(runtime.embedding_dimensions);
    const embeddingSchema = asString(runtime.embedding_input_schema_version, "not configured");
    const statusTone = (status: string): HealthCheck["status"] => {
      if (status === "succeeded") return "healthy";
      if (["pending", "running", "partial"].includes(status)) return "attention";
      return "degraded";
    };
    const runDetail = (run: UnknownRecord) => {
      const status = asString(run.status, "unknown");
      const errorCode = asString(run.error_code);
      const metrics = asRecord(run.metrics) ?? {};
      const metricSummary = Object.entries(metrics)
        .filter((entry): entry is [string, number] => typeof entry[1] === "number")
        .slice(0, 3)
        .map(([key, value]) => `${key}: ${value}`)
        .join(" · ");
      return [status, errorCode, metricSummary].filter(Boolean).join(" · ");
    };
    const health: HealthCheck[] = runs.slice(0, 6).map((run) => ({
      name: `${asString(run.run_type, "processing")} run`,
      status: statusTone(asString(run.status)),
      detail: runDetail(run) || "No metrics reported",
      checkedAt: asString(run.completed_at) || asString(run.started_at) || asString(run.created_at) || "Not reported",
    }));
    const queuedByType = new Map<string, UnknownRecord[]>();
    runs.filter((run) => ["pending", "running"].includes(asString(run.status))).forEach((run) => {
      const type = asString(run.run_type, "processing");
      queuedByType.set(type, [...(queuedByType.get(type) ?? []), run]);
    });
    const queue = Array.from(queuedByType, ([name, queuedRuns]) => ({
      name,
      depth: queuedRuns.length,
      oldest: queuedRuns.map((run) => asString(run.created_at)).filter(Boolean).sort()[0] ?? "Not reported",
      status: queuedRuns.some((run) => asString(run.status) === "running") ? "Running" : "Pending",
    }));
    const exceptions = runs
      .filter((run) => ["partial", "failed"].includes(asString(run.status)))
      .map((run) => ({
        id: asString(run.id, "unavailable"),
        type: asString(run.error_code) || asString(run.status, "unknown"),
        source: asString(run.source, "Not reported"),
        detectedAt: asString(run.completed_at) || asString(run.created_at, "Not reported"),
        detail: runDetail(run) || "The service returned no exception detail.",
      }));
    const smtpConfigured = asBoolean(notification.smtp_configured);
    const smtpDeliveryEnabled = asBoolean(notification.smtp_delivery_enabled);
    return {
      data: {
        notification: {
          targetEmail: asString(notification.target_email),
          enabled: asBoolean(notification.enabled),
          smtpDeliveryEnabled,
          smtpConfigured,
          queuedDeliveries: asNumber(notification.queued_deliveries),
          failedDeliveries: asNumber(notification.failed_deliveries),
          lastDeliveredAt: asString(notification.last_delivered_at) || undefined,
          updatedAt: asString(notification.updated_at) || undefined,
        },
        corpus: {
          backfillYears: asNumber(runtime.corpus_backfill_years),
          activeRetentionYears: asNumber(runtime.corpus_active_retention_years),
        },
        health,
        queue,
        exceptions,
        versions: [
          { component: "Application", version: asString(runtime.application_version, "not configured"), activatedAt: "Current runtime", status: "Active" },
          { component: "Drug scope rule", version: asString(runtime.scope_rule_version, "not configured"), activatedAt: "Current runtime", status: "Active" },
          { component: "HTML parser", version: asString(runtime.parser_version, "not configured"), activatedAt: "Current runtime", status: "Active" },
          { component: "Taxonomy", version: asString(runtime.taxonomy_version, "not configured"), activatedAt: "Current runtime", status: "Active" },
          { component: "Chunker", version: asString(runtime.chunker_version, "not configured"), activatedAt: "Current runtime", status: "Active" },
          {
            component: "Grounded answer model",
            version: modelId,
            activatedAt: `Prompt ${promptVersion}`,
            status: aiConfigured ? "Active" : "Disabled",
          },
          {
            component: "Retrieval embeddings",
            version: `${embeddingModelId} · ${embeddingDimensions || "?"}d`,
            activatedAt: `Schema ${embeddingSchema}`,
            status: embeddingEnabled ? "Active" : "Disabled",
          },
        ],
        controls: [
          {
            control: "Drug corpus admission configuration",
            status: asString(runtime.scope_rule_version) ? "Passing" : "Attention",
            evidence: `Runtime scope rule: ${asString(runtime.scope_rule_version, "not reported")}`,
          },
          {
            control: "Grounded AI configuration",
            status: aiConfigured ? "Passing" : "Attention",
            evidence: aiConfigured
              ? `${asString(runtime.ai_provider)} · ${modelId} · prompt ${promptVersion}`
              : "The backend reports that an AI provider is not configured.",
          },
          {
            control: "Semantic retrieval configuration",
            status: embeddingEnabled ? "Passing" : "Attention",
            evidence: embeddingEnabled
              ? `${asString(runtime.embedding_provider)} · ${embeddingModelId} · ${embeddingDimensions} dimensions · ${embeddingSchema}`
              : `Semantic embeddings are disabled; lexical retrieval remains active. Configured space: ${embeddingModelId} · ${embeddingDimensions} dimensions · ${embeddingSchema}.`,
          },
          {
            control: "Email delivery configuration",
            status: smtpConfigured && smtpDeliveryEnabled ? "Passing" : "Attention",
            evidence: smtpConfigured
              ? smtpDeliveryEnabled ? "SMTP sender and delivery are enabled." : "SMTP sender exists, but delivery is disabled."
              : "The backend reports that an SMTP sender is not configured.",
          },
        ],
        backupAge: "Not reported by service",
        lastRestoreTest: "Not reported by service",
      },
      mode: "live",
    };
  } catch (error) {
    throw error instanceof Error ? error : new Error("Administration service unavailable");
  }
}

export async function updateNotificationSettings(
  targetEmail: string,
  enabled: boolean,
): Promise<AdminData["notification"]> {
  const payload = await requestApi("/api/v1/admin/notification-settings", {
    method: "PATCH",
    body: JSON.stringify({ target_email: targetEmail, enabled }),
  });
  const result = unwrapOne(payload);
  const confirmedEmail = asString(result?.target_email);
  const confirmedEnabled = asBoolean(result?.enabled);
  if (!confirmedEmail || confirmedEmail.toLocaleLowerCase() !== targetEmail.toLocaleLowerCase()) {
    throw new Error("API returned an invalid notification-settings confirmation");
  }
  if (confirmedEnabled !== enabled) {
    throw new Error("API returned an invalid notification-settings confirmation");
  }
  return {
    targetEmail: confirmedEmail,
    enabled: confirmedEnabled,
    smtpDeliveryEnabled: asBoolean(result?.smtp_delivery_enabled),
    smtpConfigured: asBoolean(result?.smtp_configured),
    queuedDeliveries: asNumber(result?.queued_deliveries),
    failedDeliveries: asNumber(result?.failed_deliveries),
    lastDeliveredAt: asString(result?.last_delivered_at) || undefined,
    updatedAt: asString(result?.updated_at) || undefined,
  };
}

export async function queryRag(
  question: string,
  filters: RagFilter,
  language: "auto" | "en" | "ko" = "auto",
  maxSources = 6,
  conversationHistory: RagConversationMessage[] = [],
  options: RagQueryOptions = {},
  signal?: AbortSignal,
): Promise<ApiResult<RagAnswer>> {
  const payload = await requestApi("/api/v1/rag/query", {
    method: "POST",
    signal,
    body: JSON.stringify(buildRagRequestBody(
      question,
      filters,
      language,
      maxSources,
      conversationHistory,
      options,
    )),
  });
  const record = unwrapOne(payload);
  const answer = normalizeRagAnswer(record, filters, options);
  if (!answer) throw new Error("RAG endpoint returned an invalid answer");
  return { data: answer, mode: "live" };
}

function buildRagRequestBody(
  question: string,
  filters: RagFilter,
  language: "auto" | "en" | "ko",
  maxSources: number,
  conversationHistory: RagConversationMessage[],
  options: RagQueryOptions,
) {
  return {
    question,
    filters: {
      letter_id: filters.letterId,
      company: filters.company,
      category: filters.category,
      regulation: filters.regulation,
      drug_subtype: filters.subtype,
      issuing_office: filters.issuingOffice,
      issue_date_from: filters.dateFrom,
      issue_date_to: filters.dateTo,
      posted_from: filters.postedFrom,
      posted_to: filters.postedTo,
    },
    max_sources: Math.min(10, Math.max(1, Math.round(maxSources))),
    ...(options.threadId ? {} : { conversation_history: conversationHistory.slice(-8) }),
    thread_id: options.threadId,
    client_message_id: options.clientMessageId,
    retrieval_mode: options.retrievalMode ?? "auto",
    model_profile: options.modelProfile ?? "auto",
    product_scope: "Drugs",
    language,
  };
}

export async function queryRagStream(
  question: string,
  filters: RagFilter,
  language: "auto" | "en" | "ko" = "auto",
  maxSources = 6,
  conversationHistory: RagConversationMessage[] = [],
  options: RagQueryOptions = {},
  signal?: AbortSignal,
): Promise<Response> {
  if (!API_BASE_URL) throw new Error("API_BASE_URL is not configured");

  const token = await getBackendBearerAssertion();
  const headers = new Headers({
    Accept: "application/x-ndjson",
    "Content-Type": "application/json",
  });
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!token && isLocalApi(API_BASE_URL)) {
    headers.set("X-Dev-User", process.env.API_DEV_USER ?? "portal-dev");
    headers.set(
      "X-Dev-Roles",
      process.env.API_DEV_ROLES ?? process.env.APP_DEMO_ROLES ?? "viewer",
    );
  } else if (!token) {
    throw new Error("An authenticated server session is required for the configured API origin");
  }

  // Embedding retrieval and one validated model retry may legitimately exceed a minute.
  // Keep the proxy deadline below the route limit while preserving client cancellation.
  const timeoutSignal = AbortSignal.timeout(110_000);
  const combinedSignal = signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;
  return fetch(`${API_BASE_URL}/api/v1/rag/query/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(buildRagRequestBody(
      question,
      filters,
      language,
      maxSources,
      conversationHistory,
      options,
    )),
    cache: "no-store",
    signal: combinedSignal,
  });
}

export async function updateReview(
  summaryId: string,
  state: ReviewState,
  reason: string,
  options: { editedFinding?: string; expectedVersion?: string } = {},
): Promise<ReviewReceipt> {
  const decision = state === "approved" ? "approve" : state === "rejected" ? "reject" : "needs_revision";
  const requestBody: Record<string, unknown> = {
    decision,
    reason,
    expected_summary_version: options.expectedVersion,
  };
  if (options.editedFinding !== undefined) {
    requestBody.edited_executive_summary = options.editedFinding;
  }
  const payload = await requestApi(`/api/v1/reviews/${encodeURIComponent(summaryId)}`, {
    method: "PATCH",
    body: JSON.stringify(requestBody),
  });
  const result = unwrapOne(payload);
  const reviewId = asString(first(result ?? {}, "review_id"));
  const sourceSummaryId = asString(first(result ?? {}, "source_summary_id"));
  const resultingId = asString(first(result ?? {}, "resulting_summary_id"));
  const documentVersionId = asString(first(result ?? {}, "source_document_version_id"));
  const confirmedState = asString(first(result ?? {}, "review_state"));
  const reviewedBy = asString(first(result ?? {}, "reviewed_by"));
  const reviewedAt = asString(first(result ?? {}, "reviewed_at"));
  const requestId = asString(first(result ?? {}, "request_id"));
  const resultingRevision = asNumber(first(result ?? {}, "resulting_revision"), 0);

  if (!reviewId || !sourceSummaryId || !resultingId || !documentVersionId ||
      !reviewedBy || !reviewedAt || !requestId || resultingRevision < 1 || confirmedState !== state) {
    throw new Error("API returned an invalid review confirmation");
  }

  return {
    reviewId,
    sourceSummaryId,
    resultingSummaryId: resultingId,
    sourceDocumentVersionId: documentVersionId,
    resultingRevision,
    state,
    reviewedBy,
    reviewedAt,
    contentChanged: asBoolean(first(result ?? {}, "content_changed")),
    requestId,
  };
}

export async function requestReprocess(
  letterId: string,
  reason: string,
): Promise<{ accepted: true; jobId: string }> {
  const payload = await requestApi(`/api/v1/admin/letters/${encodeURIComponent(letterId)}/reprocess`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ reason }),
  });
  const result = unwrapOne(payload);
  const jobId = asString(first(result ?? {}, "job_id"));

  if (!jobId) {
    throw new Error("API returned an invalid reprocess confirmation");
  }

  return { accepted: true, jobId };
}

export async function requestCorpusSync(): Promise<{ accepted: true; runId: string; status: string }> {
  const day = new Date().toISOString().slice(0, 10);
  const source = "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters";
  const payload = await requestApi("/api/v1/admin/ingestion-runs", {
    method: "POST",
    headers: { "Idempotency-Key": `portal-corpus-sync-${day}` },
    body: JSON.stringify({
      run_type: "discovery",
      source,
      reason: "Administrator requested the rolling three-year warning-letter corpus sync.",
      options: { backfill_years: 3, active_retention_years: 5 },
    }),
  });
  const result = unwrapOne(payload);
  const runId = asString(first(result ?? {}, "id"));
  const status = asString(first(result ?? {}, "status"));
  if (!runId || !status) throw new Error("API returned an invalid corpus-sync confirmation");
  return { accepted: true, runId, status };
}
