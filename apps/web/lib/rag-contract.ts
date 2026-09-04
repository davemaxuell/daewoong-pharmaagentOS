import type {
  ChatModelProfile,
  ChatRetrievalStrategy,
  RagAnswer,
  RagCitation,
  RagFilter,
  RagQueryOptions,
} from "@/lib/types";

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as UnknownRecord
    : undefined;
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asBoolean(value: unknown, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

function first(record: UnknownRecord, ...keys: string[]) {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null) return record[key];
  }
  return undefined;
}

function normalizeFilter(value: unknown): RagFilter {
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

function normalizeCitation(value: unknown, index: number): RagCitation | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const letterId = asString(first(record, "warning_letter_id", "letter_id", "letterId"));
  const excerpt = asString(record.excerpt);
  if (!letterId || !excerpt) return undefined;
  return {
    id: asString(first(record, "chunk_id", "id"), `citation-${index + 1}`),
    letterId,
    company: asString(first(record, "company_name", "company"), "FDA Drug letter"),
    title: asString(record.title, "Official FDA source evidence"),
    issueDate: asString(first(record, "issue_date", "issueDate")),
    postedDate: asString(first(record, "posted_date", "postedDate")),
    documentType: asString(first(record, "document_type", "documentType"), "Warning letter"),
    anchor: asString(first(record, "source_anchor", "anchor"), "source"),
    excerpt,
    sourceUrl: asString(first(record, "source_url", "sourceUrl"), "https://www.fda.gov/"),
    score: asNumber(record.score),
    documentVersionId: asString(
      first(record, "document_version_id", "documentVersionId"),
    ) || undefined,
    sourceVersion: asString(first(record, "source_version", "sourceVersion")) || undefined,
    sourceHash: asString(first(record, "source_hash", "sourceHash")) || undefined,
  };
}

function normalizeModelProfile(value: unknown, fallback: ChatModelProfile = "auto") {
  return ["auto", "fast", "balanced", "deep"].includes(asString(value))
    ? asString(value) as ChatModelProfile
    : fallback;
}

function normalizeRetrievalStrategy(
  value: unknown,
  fallback: ChatRetrievalStrategy,
): ChatRetrievalStrategy {
  const strategy = asString(value);
  return ["none", "metadata", "letter", "multi_letter", "corpus"].includes(strategy)
    ? strategy as ChatRetrievalStrategy
    : fallback;
}

export function normalizeRagAnswer(
  value: unknown,
  filters: RagFilter,
  options: RagQueryOptions = {},
): RagAnswer | undefined {
  const record = asRecord(value);
  const answerText = asString(record?.answer);
  if (!record || !answerText) return undefined;

  const rawCitations = Array.isArray(record.citations) ? record.citations : [];
  const citations = rawCitations
    .map(normalizeCitation)
    .filter((citation): citation is RagCitation => Boolean(citation));
  const applied = first(record, "filters_applied", "filtersApplied") ?? {};
  const requestedModelProfile = normalizeModelProfile(
    first(record, "requested_model_profile", "requestedModelProfile"),
    options.modelProfile ?? "auto",
  );
  const effectiveModelProfileValue = normalizeModelProfile(
    first(record, "effective_model_profile", "effectiveModelProfile"),
  );
  const effectiveModelId = asString(
    first(record, "effective_model_id", "effectiveModelId"),
  ) || undefined;
  const attemptedModelId = asString(
    first(record, "attempted_model_id", "attemptedModelId"),
  ) || undefined;
  const generationUsed = asBoolean(
    first(record, "generation_used", "generationUsed"),
    Boolean(effectiveModelId && effectiveModelId !== "none"),
  );
  const interpretationValue = asString(
    first(record, "interpretation_label", "interpretationLabel"),
    "source_facts",
  );
  const interpretationLabel = ["source_facts", "ai_synthesis", "internal_comparison"].includes(
    interpretationValue,
  ) ? interpretationValue as RagAnswer["interpretationLabel"] : "source_facts";
  const evidenceValue = asString(
    first(record, "evidence_sufficiency", "evidenceSufficiency"),
    citations.length ? "sufficient" : "insufficient",
  );
  const evidenceSufficiency = ["sufficient", "partial", "insufficient"].includes(evidenceValue)
    ? evidenceValue as RagAnswer["evidenceSufficiency"]
    : citations.length ? "sufficient" : "insufficient";

  return {
    answer: answerText,
    interpretationLabel,
    scopeLabel: "FDA Product: Drugs",
    filtersApplied: normalizeFilter(applied),
    evidenceSufficiency,
    citations,
    generatedAt: asString(
      first(record, "generated_at", "generatedAt"),
      new Date().toISOString(),
    ),
    requestId: asString(
      first(record, "query_id", "request_id", "requestId"),
      "request-unavailable",
    ),
    threadId: asString(first(record, "thread_id", "threadId")) || options.threadId || undefined,
    userMessageId: asString(first(record, "user_message_id", "userMessageId")) || undefined,
    assistantMessageId: asString(
      first(record, "assistant_message_id", "assistantMessageId"),
    ) || undefined,
    retrievalStrategy: normalizeRetrievalStrategy(
      first(record, "retrieval_strategy", "retrievalStrategy"),
      filters.letterId ? "letter" : "corpus",
    ),
    routeReason: asString(first(record, "route_reason", "routeReason")) || undefined,
    requestedModelProfile,
    effectiveModelProfile: effectiveModelProfileValue === "auto"
      ? undefined
      : effectiveModelProfileValue,
    effectiveModelId,
    attemptedModelId,
    generationUsed,
    focusedDocumentVersionId: asString(
      first(record, "focused_document_version_id", "focusedDocumentVersionId"),
    ) || undefined,
  };
}

export type RagStreamPhase = "retrieving" | "generating" | "validating";

export type RagStreamEvent =
  | { type: "phase"; phase: RagStreamPhase }
  | { type: "draft_delta"; attempt: number; text: string }
  | { type: "draft_reset"; attempt: number }
  | { type: "complete"; data: RagAnswer }
  | { type: "error"; code: string; message: string };

export function normalizeRagStreamEvent(
  value: unknown,
  filters: RagFilter,
  options: RagQueryOptions,
): RagStreamEvent | undefined {
  const record = asRecord(value);
  const type = asString(record?.type);
  if (!record) return undefined;
  if (type === "phase") {
    const phase = asString(record.phase);
    return ["retrieving", "generating", "validating"].includes(phase)
      ? { type, phase: phase as RagStreamPhase }
      : undefined;
  }
  if (type === "draft_delta") {
    const attempt = asNumber(record.attempt);
    const text = asString(record.text);
    return attempt >= 1 && text ? { type, attempt, text } : undefined;
  }
  if (type === "draft_reset") {
    const attempt = asNumber(record.attempt);
    return attempt >= 1 ? { type, attempt } : undefined;
  }
  if (type === "complete") {
    const data = normalizeRagAnswer(record.data, filters, options);
    return data ? { type, data } : undefined;
  }
  if (type === "error") {
    const code = asString(record.code, "stream_failed");
    const message = asString(record.message);
    return message ? { type, code, message } : undefined;
  }
  return undefined;
}
