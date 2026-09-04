import "server-only";

import { getBackendBearerAssertion } from "@/lib/backend-auth";
import {
  parseAgentCase,
  parseAgentCasePage,
  parseCaseEventPage,
  parseCasePlan,
  parseCaseRun,
  parseArtifactPage,
  parseImpactMap,
  parseIntegrationDraftPage,
  parseRunEventPage,
  parseSingleArtifact,
  parseSingleIntegrationDraft,
  parseVerificationReport,
  type AgentCase,
  type AgentCasePage,
  type ArtifactPage,
  type ArtifactVersion,
  type CaseEventPage,
  type CasePlan,
  type CaseRun,
  type ImpactHypothesis,
  type ImpactMap,
  type IntegrationDraft,
  type IntegrationDraftPage,
  type CaseStatus,
  type RiskLevel,
  type RunEventPage,
  type StepLimits,
  type VerificationReport,
} from "@/lib/case-types";

type UnknownRecord = Record<string, unknown>;

export class CaseApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "CaseApiError";
  }
}

export type CreateCaseInput = {
  title: string;
  objective: string;
  workflowKey: string;
  warningLetterId: string;
  documentVersionId: string;
  sourceRole?: "PRIMARY_REGULATORY" | "SUPPORTING_REGULATORY";
};

export type CasePlanStepInput = {
  stepKey: string;
  title: string;
  instructions: string;
  dependsOn: string[];
  agentVersionId?: string;
  skillVersionIds?: string[];
  toolVersionIds?: string[];
  outputSchemaRef: string;
  riskLevel: RiskLevel;
  requiresApproval?: boolean;
  limits?: Partial<StepLimits>;
};

export type CreateCasePlanInput = {
  objective?: string;
  steps: CasePlanStepInput[];
  assignedReviewerId?: string;
};

const API_BASE_URL = process.env.API_BASE_URL?.replace(/\/$/, "");

/**
 * Event history is loaded in bounded pages so the case workspace never presents
 * a single-page excerpt as the complete audit trail. The hard ceiling protects
 * server rendering from an unbounded upstream pagination loop; callers receive
 * an explicit error instead of a silently truncated history.
 */
export const CASE_EVENT_PAGE_LIMIT = 200;
export const CASE_EVENT_MAX_PAGES = 50;

function asRecord(value: unknown): UnknownRecord | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as UnknownRecord
    : undefined;
}

async function requestCaseApi(path: string, init: RequestInit = {}): Promise<unknown> {
  if (!API_BASE_URL) {
    throw new CaseApiError(
      0,
      "The case service is not configured. Set API_BASE_URL to use governed case records.",
    );
  }

  const bearerAssertion = await getBackendBearerAssertion();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${bearerAssertion}`);
  if (init.body) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      cache: "no-store",
      signal: init.signal
        ? AbortSignal.any([init.signal, AbortSignal.timeout(8_000)])
        : AbortSignal.timeout(8_000),
    });
  } catch (error) {
    if (error instanceof CaseApiError) throw error;
    throw new CaseApiError(0, "The governed case service could not be reached.");
  }

  if (!response.ok) {
    let detail = "The case service rejected the request.";
    let requestId = response.headers.get("x-request-id") ?? undefined;
    try {
      const problem = asRecord(await response.json());
      if (typeof problem?.detail === "string") detail = problem.detail;
      if (typeof problem?.request_id === "string") requestId = problem.request_id;
    } catch {
      // Avoid reflecting arbitrary upstream response bodies into the portal.
    }
    throw new CaseApiError(response.status, detail, requestId);
  }

  return response.status === 204 ? null : response.json() as Promise<unknown>;
}

function planStepPayload(step: CasePlanStepInput) {
  const limits = step.limits;
  return {
    step_key: step.stepKey,
    title: step.title,
    instructions: step.instructions,
    depends_on: step.dependsOn,
    agent_version_id: step.agentVersionId,
    skill_version_ids: step.skillVersionIds ?? [],
    tool_version_ids: step.toolVersionIds ?? [],
    output_schema_ref: step.outputSchemaRef,
    risk_level: step.riskLevel,
    requires_approval: step.requiresApproval ?? false,
    ...(limits
      ? {
          limits: {
            max_turns: limits.maxTurns ?? 5,
            max_tool_calls: limits.maxToolCalls ?? 20,
            max_input_tokens: limits.maxInputTokens ?? 100_000,
            max_output_tokens: limits.maxOutputTokens ?? 20_000,
            max_runtime_seconds: limits.maxRuntimeSeconds ?? 300,
            max_cost_usd: limits.maxCostUsd ?? 5,
          },
        }
      : {}),
  };
}

export async function listAgentCases(status?: CaseStatus): Promise<AgentCasePage> {
  const query = new URLSearchParams({ limit: "100" });
  if (status) query.set("status", status);
  return parseAgentCasePage(await requestCaseApi(`/api/v1/cases?${query.toString()}`));
}

export async function getAgentCase(caseId: string): Promise<AgentCase> {
  return parseAgentCase(await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}`));
}

export async function getAgentCaseEvents(caseId: string): Promise<CaseEventPage> {
  const items: CaseEventPage["items"] = [];
  const seenCursors = new Set<string>();
  let cursor: string | null = null;

  for (let pageNumber = 1; pageNumber <= CASE_EVENT_MAX_PAGES; pageNumber += 1) {
    const query = new URLSearchParams({ limit: String(CASE_EVENT_PAGE_LIMIT) });
    if (cursor) query.set("cursor", cursor);

    const page = parseCaseEventPage(
      await requestCaseApi(
        `/api/v1/cases/${encodeURIComponent(caseId)}/events?${query.toString()}`,
      ),
    );
    items.push(...page.items);

    if (!page.hasMore) {
      return { items, nextCursor: null, hasMore: false };
    }
    if (!page.nextCursor) {
      throw new CaseApiError(
        0,
        "The case service returned an incomplete event-history page without a continuation cursor.",
      );
    }
    if (seenCursors.has(page.nextCursor)) {
      throw new CaseApiError(
        0,
        "The case service repeated an event-history cursor; the complete audit trail could not be loaded.",
      );
    }
    if (pageNumber === CASE_EVENT_MAX_PAGES) {
      throw new CaseApiError(
        0,
        `Case event history exceeds the ${CASE_EVENT_MAX_PAGES}-page safety limit (up to ${CASE_EVENT_MAX_PAGES * CASE_EVENT_PAGE_LIMIT} events); the complete audit trail was not loaded.`,
      );
    }

    seenCursors.add(page.nextCursor);
    cursor = page.nextCursor;
  }

  // The loop either returns a complete history or throws at its explicit bound.
  throw new CaseApiError(0, "The complete case event history could not be loaded.");
}

export async function getAgentCasePlan(caseId: string, version: number): Promise<CasePlan> {
  return parseCasePlan(
    await requestCaseApi(
      `/api/v1/cases/${encodeURIComponent(caseId)}/plans/${encodeURIComponent(String(version))}`,
    ),
  );
}

export async function createAgentCase(
  input: CreateCaseInput,
  idempotencyKey: string,
): Promise<AgentCase> {
  const payload = await requestCaseApi("/api/v1/cases", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      title: input.title,
      objective: input.objective,
      workflow_key: input.workflowKey,
      warning_letter_id: input.warningLetterId,
      document_version_id: input.documentVersionId,
      source_role: input.sourceRole ?? "PRIMARY_REGULATORY",
    }),
  });
  return parseAgentCase(payload);
}

export async function createAgentCasePlan(
  caseId: string,
  input: CreateCasePlanInput,
  idempotencyKey: string,
): Promise<CasePlan> {
  const payload = await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}/plans`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      plan_schema_version: "1.0.0",
      objective: input.objective,
      steps: input.steps.map(planStepPayload),
      assigned_reviewer_id: input.assignedReviewerId,
    }),
  });
  return parseCasePlan(payload);
}

export async function decideAgentCasePlan(
  caseId: string,
  version: number,
  input: {
    decision: "approve" | "reject";
    expectedPlanSha256: string;
    expectedStateHash: string;
    reason?: string;
  },
  idempotencyKey: string,
): Promise<CasePlan> {
  const payload = await requestCaseApi(
    `/api/v1/cases/${encodeURIComponent(caseId)}/plans/${encodeURIComponent(String(version))}/approve`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        decision: input.decision,
        expected_plan_sha256: input.expectedPlanSha256,
        expected_state_hash: input.expectedStateHash,
        reason: input.reason,
      }),
    },
  );
  return parseCasePlan(payload);
}

export async function getAgentCaseRun(runId: string): Promise<CaseRun> {
  return parseCaseRun(
    await requestCaseApi(`/api/v1/runs/${encodeURIComponent(runId)}`),
  );
}

export async function getAgentCaseRunEvents(runId: string): Promise<RunEventPage> {
  const items: RunEventPage["items"] = [];
  let cursor: string | null = null;
  const seenCursors = new Set<string>();
  for (let pageNumber = 1; pageNumber <= CASE_EVENT_MAX_PAGES; pageNumber += 1) {
    const query = new URLSearchParams({ limit: "500" });
    if (cursor) query.set("cursor", cursor);
    const page = parseRunEventPage(
      await requestCaseApi(
        `/api/v1/runs/${encodeURIComponent(runId)}/events?${query.toString()}`,
      ),
    );
    items.push(...page.items);
    if (!page.hasMore) return { items, nextCursor: null, hasMore: false };
    if (!page.nextCursor || seenCursors.has(page.nextCursor)) {
      throw new CaseApiError(0, "The complete run timeline could not be loaded.");
    }
    seenCursors.add(page.nextCursor);
    cursor = page.nextCursor;
  }
  throw new CaseApiError(0, "The run timeline exceeds the safe rendering limit.");
}

export async function startAgentCaseRun(
  caseId: string,
  plan: Pick<CasePlan, "version" | "planSha256" | "basedOnStateHash">,
  idempotencyKey: string,
): Promise<CaseRun> {
  return parseCaseRun(
    await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}/runs`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        plan_version: plan.version,
        expected_plan_sha256: plan.planSha256,
        expected_state_hash: plan.basedOnStateHash,
      }),
    }),
  );
}

export async function controlAgentCaseRun(
  runId: string,
  operation: "pause" | "resume" | "cancel",
  reason: string,
  idempotencyKey: string,
): Promise<CaseRun> {
  return parseCaseRun(
    await requestCaseApi(
      `/api/v1/runs/${encodeURIComponent(runId)}/${operation}`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({ reason }),
      },
    ),
  );
}

export async function decideAgentRunStep(
  runId: string,
  stepKey: string,
  input: { decision: "approve" | "reject"; approvalId: string; reason: string },
  idempotencyKey: string,
): Promise<CaseRun> {
  return parseCaseRun(
    await requestCaseApi(
      `/api/v1/runs/${encodeURIComponent(runId)}/steps/${encodeURIComponent(stepKey)}/approval`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({
          decision: input.decision,
          expected_approval_id: input.approvalId,
          reason: input.reason,
        }),
      },
    ),
  );
}

export async function getAgentCaseImpact(caseId: string): Promise<ImpactMap> {
  return parseImpactMap(
    await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}/impact`),
  );
}

export async function generateAgentCaseImpact(
  caseId: string,
  input: { query?: string; perFindingLimit?: number },
  idempotencyKey: string,
): Promise<ImpactMap> {
  return parseImpactMap(
    await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}/impact/generate`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        query: input.query || undefined,
        per_finding_limit: input.perFindingLimit ?? 5,
      }),
    }),
  );
}

export async function decideAgentCaseImpact(
  caseId: string,
  hypothesisId: string,
  input: {
    decision: "accept" | "reject";
    expectedHypothesisSha256: string;
    reason: string;
  },
  idempotencyKey: string,
): Promise<ImpactHypothesis> {
  const result = await requestCaseApi(
    `/api/v1/cases/${encodeURIComponent(caseId)}/impact/${encodeURIComponent(hypothesisId)}/decision`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        decision: input.decision,
        expected_hypothesis_sha256: input.expectedHypothesisSha256,
        reason: input.reason,
      }),
    },
  );
  return parseImpactMap({
    case_id: caseId,
    generated_count: 0,
    items: [result],
    notice: "Decision-support hypothesis.",
  }).items[0];
}

export async function getAgentCaseVerification(
  caseId: string,
): Promise<VerificationReport | null> {
  return parseVerificationReport(
    await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}/verification/latest`),
  );
}

export async function verifyAgentCase(
  caseId: string,
  idempotencyKey: string,
): Promise<VerificationReport> {
  const report = parseVerificationReport(
    await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}/verification`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  );
  if (!report) throw new Error("Verification response was unexpectedly empty.");
  return report;
}

export async function getAgentCaseArtifacts(caseId: string): Promise<ArtifactPage> {
  return parseArtifactPage(
    await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}/artifacts`),
  );
}

export async function composeAgentCaseArtifact(
  caseId: string,
  input: { title: string; assignedReviewerId?: string },
  idempotencyKey: string,
): Promise<ArtifactVersion> {
  return parseSingleArtifact(
    await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}/artifacts/compose`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        title: input.title,
        assigned_reviewer_id: input.assignedReviewerId || undefined,
      }),
    }),
  );
}

export async function decideAgentCaseArtifact(
  caseId: string,
  artifactVersionId: string,
  input: {
    decision: "approve" | "reject" | "request_revision";
    expectedContentSha256: string;
    expectedEvidenceManifestSha256: string;
    reason: string;
  },
  idempotencyKey: string,
): Promise<ArtifactVersion> {
  return parseSingleArtifact(
    await requestCaseApi(
      `/api/v1/cases/${encodeURIComponent(caseId)}/artifacts/${encodeURIComponent(artifactVersionId)}/decision`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({
          decision: input.decision,
          expected_content_sha256: input.expectedContentSha256,
          expected_evidence_manifest_sha256: input.expectedEvidenceManifestSha256,
          reason: input.reason,
        }),
      },
    ),
  );
}

export async function getAgentCaseIntegrationDrafts(
  caseId: string,
): Promise<IntegrationDraftPage> {
  return parseIntegrationDraftPage(
    await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}/integration-drafts`),
  );
}

export async function createAgentCaseIntegrationDraft(
  caseId: string,
  input: {
    channel: IntegrationDraft["channel"];
    destination: string;
    title: string;
    body: string;
    runId?: string;
  },
  idempotencyKey: string,
): Promise<IntegrationDraft> {
  return parseSingleIntegrationDraft(
    await requestCaseApi(`/api/v1/cases/${encodeURIComponent(caseId)}/integration-drafts`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        channel: input.channel,
        destination: input.destination,
        title: input.title,
        body: input.body,
        run_id: input.runId,
      }),
    }),
  );
}

export async function reviewAgentCaseIntegrationDraft(
  draftId: string,
  input: {
    decision: "review_for_manual_use" | "cancel";
    expectedContentSha256: string;
    reason: string;
  },
): Promise<IntegrationDraft> {
  return parseSingleIntegrationDraft(
    await requestCaseApi(`/api/v1/integration-drafts/${encodeURIComponent(draftId)}/review`, {
      method: "POST",
      body: JSON.stringify({
        decision: input.decision,
        expected_content_sha256: input.expectedContentSha256,
        reason: input.reason,
      }),
    }),
  );
}
