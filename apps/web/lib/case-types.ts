export const CASE_STATUSES = [
  "DRAFT",
  "PLANNING",
  "AWAITING_PLAN_APPROVAL",
  "READY",
  "RUNNING",
  "WAITING_FOR_INPUT",
  "WAITING_FOR_REVIEW",
  "NEEDS_REVISION",
  "COMPLETED",
  "BLOCKED",
  "FAILED",
  "CANCELLED",
  "STALE",
] as const;

export type CaseStatus = (typeof CASE_STATUSES)[number];
export type CaseStatusTone = "neutral" | "attention" | "ready" | "active" | "closed" | "danger";
export type CaseWorkspaceView = "overview" | "plan" | "execution" | "impact" | "review" | "integrations" | "evidence" | "history";
export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED" | "EXPIRED";
export type RiskLevel = "R0" | "R1" | "R2" | "R3";

export type CaseSource = {
  id: string;
  caseId: string;
  warningLetterId: string;
  documentId: string;
  documentVersionId: string;
  documentVersionNumber: number;
  sourceRole: string;
  sourceSha256: string;
  sourceUrl: string;
  pinnedBy: string;
  createdAt: string;
  immutable: true;
};

export type AgentCase = {
  id: string;
  title: string;
  objective: string;
  status: CaseStatus;
  ownerSubject: string;
  workflowKey: string;
  currentStateHash: string;
  sources: CaseSource[];
  createdAt: string;
  updatedAt: string;
};

export type AgentCasePage = {
  items: AgentCase[];
  nextCursor: string | null;
  hasMore: boolean;
};

export type StepLimits = {
  maxTurns: number;
  maxToolCalls: number;
  maxInputTokens: number;
  maxOutputTokens: number;
  maxRuntimeSeconds: number;
  maxCostUsd: number;
};

export type CasePlanStep = {
  id: string;
  position: number;
  stepKey: string;
  title: string;
  instructions: string;
  dependsOn: string[];
  agentVersionId: string | null;
  skillVersionIds: string[];
  toolVersionIds: string[];
  outputSchemaRef: string;
  riskLevel: RiskLevel;
  requiresApproval: boolean;
  limits: StepLimits;
  createdAt: string;
};

export type PlanApproval = {
  id: string;
  approvalType: string;
  status: ApprovalStatus;
  requestedBy: string;
  assignedReviewerId: string | null;
  decisionBy: string | null;
  decisionReason: string | null;
  decidedAt: string | null;
  expiresAt: string | null;
  planSha256: string;
  boundStateHash: string;
  createdAt: string;
};

export type CasePlan = {
  id: string;
  caseId: string;
  version: number;
  objective: string;
  planSchemaVersion: string;
  planSha256: string;
  basedOnStateHash: string;
  workflowTemplateVersionId: string | null;
  prohibitedActions: string[];
  createdBy: string;
  createdAt: string;
  steps: CasePlanStep[];
  approval: PlanApproval;
};

export type CaseEvent = {
  id: string;
  caseId: string;
  sequence: number;
  eventType: string;
  actorType: string;
  actorId: string;
  requestId: string;
  payload: Record<string, unknown>;
  previousEventHash: string | null;
  eventHash: string;
  stateHash: string;
  occurredAt: string;
};

export type CaseEventPage = {
  items: CaseEvent[];
  nextCursor: string | null;
  hasMore: boolean;
};

export const RUN_STATUSES = [
  "PENDING",
  "RUNNING",
  "PAUSED",
  "WAITING_FOR_APPROVAL",
  "COMPLETED",
  "BLOCKED",
  "FAILED",
  "CANCELLED",
] as const;

export const INVOCATION_STATUSES = [
  "PENDING",
  "RUNNING",
  "WAITING_FOR_APPROVAL",
  "COMPLETED",
  "BLOCKED",
  "FAILED",
  "CANCELLED",
] as const;

export type AgentRunStatus = (typeof RUN_STATUSES)[number];
export type InvocationStatus = (typeof INVOCATION_STATUSES)[number];

export type InvocationUsage = {
  turns: number;
  toolCalls: number;
  inputTokens: number;
  outputTokens: number;
  runtimeSeconds: number;
  costUsd: number;
};

export type RunStepState = {
  status: InvocationStatus;
  attempt: number;
  invocationId: string | null;
  approvalId: string | null;
  outputSha256: string | null;
  usage: InvocationUsage;
};

export type AgentInvocation = {
  id: string;
  runId: string;
  caseId: string;
  planStepId: string;
  stepKey: string;
  attempt: number;
  agentVersionId: string | null;
  status: InvocationStatus;
  outputSchemaRef: string;
  inputSha256: string;
  outputSha256: string | null;
  limits: Record<string, unknown>;
  usage: InvocationUsage;
  errorCode: string | null;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string;
};

export type CaseRun = {
  id: string;
  caseId: string;
  planId: string;
  planVersion: number;
  planSha256: string;
  boundStateHash: string;
  status: AgentRunStatus;
  requestedBy: string;
  checkpoint: {
    schemaVersion: "pharmaagent-run-state@1.0.0";
    checkpointVersion: number;
    stepKey: string | null;
    workflowTemplate: {
      id: string;
      workflowKey: string;
      version: string;
      manifestSha256: string;
    };
    steps: Record<string, RunStepState>;
    budget: InvocationUsage;
    pauseRequested: boolean;
    cancelRequested: boolean;
  };
  activeInvocation: AgentInvocation | null;
  errorCode: string | null;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string;
};

export type RunEvent = {
  id: string;
  runId: string;
  caseId: string;
  sequence: number;
  eventType: string;
  actorType: string;
  actorId: string;
  requestId: string;
  payload: Record<string, unknown>;
  previousEventHash: string | null;
  eventHash: string;
  occurredAt: string;
};

export type RunEventPage = {
  items: RunEvent[];
  nextCursor: string | null;
  hasMore: boolean;
};

export type EvidenceReference = {
  sourceType: "EXTERNAL_REGULATORY" | "INTERNAL_ASSET";
  sourceVersionId: string;
  sourceHash: string;
  anchorId: string;
  excerpt: string;
  sourceUrl: string | null;
};

export type ImpactHypothesis = {
  id: string;
  caseId: string;
  runId: string | null;
  findingId: string;
  assetId: string;
  assetVersionId: string;
  assetKey: string;
  assetTitle: string;
  assetType: string;
  assetDomain: string;
  revision: number;
  effectiveStatus: string;
  relationshipType: string;
  statement: string;
  knownFacts: string[];
  derivedRelationships: string[];
  assumptions: string[];
  counterevidence: string[];
  unknowns: string[];
  recommendedVerification: string[];
  externalEvidence: EvidenceReference[];
  internalEvidence: EvidenceReference[];
  confidence: number;
  reviewPriority: string;
  status: "PROPOSED" | "ACCEPTED" | "REJECTED";
  hypothesisSha256: string;
  createdBy: string;
  reviewedBy: string | null;
  reviewReason: string | null;
  reviewedAt: string | null;
  createdAt: string;
  decisionSupportOnly: true;
};

export type ImpactMap = {
  caseId: string;
  generatedCount: number;
  items: ImpactHypothesis[];
  notice: string;
};

export type VerificationIssue = {
  severity: "CRITICAL" | "MAJOR" | "MINOR";
  code: string;
  affectedClaim: string;
  reason: string;
  supportingEvidence: string[];
  requiredCorrection: string;
  responsibleAgent: string;
};

export type VerificationReport = {
  id: string;
  caseId: string;
  planId: string;
  correctionIteration: number;
  status: "PASS" | "REVISE" | "BLOCK";
  checks: Array<{ check: string; status: "PASS" | "FAIL"; detail: string }>;
  issues: VerificationIssue[];
  verifiedHypothesisIds: string[];
  reportSha256: string;
  inputSha256: string;
  verifier: string;
  createdAt: string;
  independentContext: true;
};

export type ArtifactVersion = {
  id: string;
  artifactId: string;
  title: string;
  version: number;
  verificationReportId: string;
  content: Record<string, unknown>;
  contentSha256: string;
  evidenceManifestSha256: string;
  status: "DRAFT" | "APPROVED" | "REJECTED";
  createdAt: string;
  evidence: Array<{
    id: string;
    anchor: string;
    sourceSha256: string;
    excerptSha256: string;
    evidenceRole: string;
  }>;
  approval: {
    id: string;
    status: ApprovalStatus;
    requestedBy: string;
    assignedReviewerId: string | null;
    decisionBy: string | null;
    decisionReason: string | null;
  };
};

export type ArtifactPage = { items: ArtifactVersion[] };

export type IntegrationDraft = {
  id: string;
  caseId: string;
  runId: string | null;
  channel: "INTERNAL" | "EMAIL" | "SLACK" | "TEAMS" | "NOTION" | "TASK";
  action: "CREATE_DRAFT";
  destination: string;
  content: { title: string; body: string; decision_support_only: true; manual_delivery_required: true };
  contentSha256: string;
  status: "DRAFT" | "REVIEWED_FOR_MANUAL_USE" | "CANCELLED";
  externalDeliveryAllowed: false;
  requestedBy: string;
  reviewedBy: string | null;
  reviewReason: string | null;
  reviewedAt: string | null;
  createdAt: string;
};

export type IntegrationDraftPage = { items: IntegrationDraft[] };

export type CaseActionState = {
  status: "idle" | "error" | "success";
  message?: string;
  requestId?: string;
};

export const EMPTY_CASE_ACTION_STATE: CaseActionState = { status: "idle" };

type UnknownRecord = Record<string, unknown>;

const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function record(value: unknown, field: string): UnknownRecord {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Invalid case response: ${field} must be an object.`);
  }
  return value as UnknownRecord;
}

function stringValue(value: unknown, field: string): string;
function stringValue(value: unknown, field: string, options: { nullable: true }): string | null;
function stringValue(
  value: unknown,
  field: string,
  options: { nullable?: boolean } = {},
): string | null {
  if (options.nullable && value === null) return null;
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Invalid case response: ${field} must be a non-empty string.`);
  }
  return value;
}

function uuid(value: unknown, field: string, nullable = false): string | null {
  if (nullable && value === null) return null;
  const parsed = stringValue(value, field);
  if (!UUID_PATTERN.test(parsed)) {
    throw new Error(`Invalid case response: ${field} must be a UUID.`);
  }
  return parsed;
}

function sha256(value: unknown, field: string, nullable = false): string | null {
  if (nullable && value === null) return null;
  const parsed = stringValue(value, field);
  if (!SHA256_PATTERN.test(parsed)) {
    throw new Error(`Invalid case response: ${field} must be a lowercase SHA-256 digest.`);
  }
  return parsed;
}

function numberValue(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Invalid case response: ${field} must be a finite number.`);
  }
  return value;
}

function integer(value: unknown, field: string, minimum = 0): number {
  const parsed = numberValue(value, field);
  if (!Number.isInteger(parsed) || parsed < minimum) {
    throw new Error(`Invalid case response: ${field} must be an integer of at least ${minimum}.`);
  }
  return parsed;
}

function booleanValue(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") {
    throw new Error(`Invalid case response: ${field} must be a boolean.`);
  }
  return value;
}

function dateTime(value: unknown, field: string, nullable = false): string | null {
  if (nullable && value === null) return null;
  const parsed = stringValue(value, field);
  if (Number.isNaN(Date.parse(parsed))) {
    throw new Error(`Invalid case response: ${field} must be an ISO date-time.`);
  }
  return parsed;
}

function httpsUrl(value: unknown, field: string): string {
  const parsed = stringValue(value, field);
  let url: URL;
  try {
    url = new URL(parsed);
  } catch {
    throw new Error(`Invalid case response: ${field} must be a URL.`);
  }
  if (url.protocol !== "https:") {
    throw new Error(`Invalid case response: ${field} must use HTTPS.`);
  }
  return url.toString();
}

function stringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    throw new Error(`Invalid case response: ${field} must be a string array.`);
  }
  return [...value];
}

function enumValue<const T extends readonly string[]>(
  value: unknown,
  values: T,
  field: string,
): T[number] {
  if (typeof value !== "string" || !values.includes(value)) {
    throw new Error(`Invalid case response: ${field} has an unsupported value.`);
  }
  return value as T[number];
}

export function parseCaseSource(value: unknown): CaseSource {
  const source = record(value, "source");
  if (source.immutable !== true) {
    throw new Error("Invalid case response: source.immutable must be true.");
  }
  return {
    id: uuid(source.id, "source.id")!,
    caseId: uuid(source.case_id, "source.case_id")!,
    warningLetterId: uuid(source.warning_letter_id, "source.warning_letter_id")!,
    documentId: uuid(source.document_id, "source.document_id")!,
    documentVersionId: uuid(source.document_version_id, "source.document_version_id")!,
    documentVersionNumber: integer(source.document_version_number, "source.document_version_number", 1),
    sourceRole: stringValue(source.source_role, "source.source_role"),
    sourceSha256: sha256(source.source_sha256, "source.source_sha256")!,
    sourceUrl: httpsUrl(source.source_url, "source.source_url"),
    pinnedBy: stringValue(source.pinned_by, "source.pinned_by"),
    createdAt: dateTime(source.created_at, "source.created_at")!,
    immutable: true,
  };
}

export function parseAgentCase(value: unknown): AgentCase {
  const item = record(value, "case");
  if (!Array.isArray(item.sources)) {
    throw new Error("Invalid case response: case.sources must be an array.");
  }
  return {
    id: uuid(item.id, "case.id")!,
    title: stringValue(item.title, "case.title"),
    objective: stringValue(item.objective, "case.objective"),
    status: enumValue(item.status, CASE_STATUSES, "case.status"),
    ownerSubject: stringValue(item.owner_subject, "case.owner_subject"),
    workflowKey: stringValue(item.workflow_key, "case.workflow_key"),
    currentStateHash: sha256(item.current_state_hash, "case.current_state_hash")!,
    sources: item.sources.map(parseCaseSource),
    createdAt: dateTime(item.created_at, "case.created_at")!,
    updatedAt: dateTime(item.updated_at, "case.updated_at")!,
  };
}

export function parseAgentCasePage(value: unknown): AgentCasePage {
  const page = record(value, "case page");
  if (!Array.isArray(page.items)) {
    throw new Error("Invalid case response: case page items must be an array.");
  }
  const nextCursor = page.next_cursor === null
    ? null
    : stringValue(page.next_cursor, "case page next_cursor");
  return {
    items: page.items.map(parseAgentCase),
    nextCursor,
    hasMore: booleanValue(page.has_more, "case page has_more"),
  };
}

function parseStepLimits(value: unknown): StepLimits {
  const limits = record(value, "plan step limits");
  return {
    maxTurns: integer(limits.max_turns, "limits.max_turns", 1),
    maxToolCalls: integer(limits.max_tool_calls, "limits.max_tool_calls"),
    maxInputTokens: integer(limits.max_input_tokens, "limits.max_input_tokens", 1),
    maxOutputTokens: integer(limits.max_output_tokens, "limits.max_output_tokens", 1),
    maxRuntimeSeconds: integer(limits.max_runtime_seconds, "limits.max_runtime_seconds", 1),
    maxCostUsd: numberValue(limits.max_cost_usd, "limits.max_cost_usd"),
  };
}

function parsePlanStep(value: unknown): CasePlanStep {
  const step = record(value, "plan step");
  const nullableAgentId = uuid(step.agent_version_id, "plan step agent_version_id", true);
  return {
    id: uuid(step.id, "plan step id")!,
    position: integer(step.position, "plan step position", 1),
    stepKey: stringValue(step.step_key, "plan step key"),
    title: stringValue(step.title, "plan step title"),
    instructions: stringValue(step.instructions, "plan step instructions"),
    dependsOn: stringArray(step.depends_on, "plan step depends_on"),
    agentVersionId: nullableAgentId,
    skillVersionIds: stringArray(step.skill_version_ids, "plan step skill_version_ids").map((id) => {
      if (!UUID_PATTERN.test(id)) throw new Error("Invalid case response: skill version ID must be a UUID.");
      return id;
    }),
    toolVersionIds: stringArray(step.tool_version_ids, "plan step tool_version_ids").map((id) => {
      if (!UUID_PATTERN.test(id)) throw new Error("Invalid case response: tool version ID must be a UUID.");
      return id;
    }),
    outputSchemaRef: stringValue(step.output_schema_ref, "plan step output_schema_ref"),
    riskLevel: enumValue(step.risk_level, ["R0", "R1", "R2", "R3"] as const, "plan step risk_level"),
    requiresApproval: booleanValue(step.requires_approval, "plan step requires_approval"),
    limits: parseStepLimits(step.limits),
    createdAt: dateTime(step.created_at, "plan step created_at")!,
  };
}

function parseApproval(value: unknown): PlanApproval {
  const approval = record(value, "plan approval");
  return {
    id: uuid(approval.id, "approval.id")!,
    approvalType: stringValue(approval.approval_type, "approval.approval_type"),
    status: enumValue(
      approval.status,
      ["PENDING", "APPROVED", "REJECTED", "CANCELLED", "EXPIRED"] as const,
      "approval.status",
    ),
    requestedBy: stringValue(approval.requested_by, "approval.requested_by"),
    assignedReviewerId: stringValue(
      approval.assigned_reviewer_id,
      "approval.assigned_reviewer_id",
      { nullable: true },
    ),
    decisionBy: stringValue(approval.decision_by, "approval.decision_by", { nullable: true }),
    decisionReason: stringValue(approval.decision_reason, "approval.decision_reason", { nullable: true }),
    decidedAt: dateTime(approval.decided_at, "approval.decided_at", true),
    expiresAt: dateTime(approval.expires_at, "approval.expires_at", true),
    planSha256: sha256(approval.plan_sha256, "approval.plan_sha256")!,
    boundStateHash: sha256(approval.bound_state_hash, "approval.bound_state_hash")!,
    createdAt: dateTime(approval.created_at, "approval.created_at")!,
  };
}

export function parseCasePlan(value: unknown): CasePlan {
  const plan = record(value, "case plan");
  if (!Array.isArray(plan.steps)) {
    throw new Error("Invalid case response: case plan steps must be an array.");
  }
  return {
    id: uuid(plan.id, "case plan id")!,
    caseId: uuid(plan.case_id, "case plan case_id")!,
    version: integer(plan.version, "case plan version", 1),
    objective: stringValue(plan.objective, "case plan objective"),
    planSchemaVersion: stringValue(plan.plan_schema_version, "case plan schema version"),
    planSha256: sha256(plan.plan_sha256, "case plan SHA-256")!,
    basedOnStateHash: sha256(plan.based_on_state_hash, "case plan state hash")!,
    workflowTemplateVersionId: uuid(
      plan.workflow_template_version_id ?? null,
      "case plan workflow template version id",
      true,
    ),
    prohibitedActions: stringArray(plan.prohibited_actions, "case plan prohibited_actions"),
    createdBy: stringValue(plan.created_by, "case plan created_by"),
    createdAt: dateTime(plan.created_at, "case plan created_at")!,
    steps: plan.steps.map(parsePlanStep),
    approval: parseApproval(plan.approval),
  };
}

function parseCaseEvent(value: unknown): CaseEvent {
  const event = record(value, "case event");
  const payload = record(event.payload, "case event payload");
  return {
    id: uuid(event.id, "case event id")!,
    caseId: uuid(event.case_id, "case event case_id")!,
    sequence: integer(event.sequence, "case event sequence", 1),
    eventType: stringValue(event.event_type, "case event type"),
    actorType: stringValue(event.actor_type, "case event actor_type"),
    actorId: stringValue(event.actor_id, "case event actor_id"),
    requestId: stringValue(event.request_id, "case event request_id"),
    payload: { ...payload },
    previousEventHash: sha256(event.previous_event_hash, "case event previous hash", true),
    eventHash: sha256(event.event_hash, "case event hash")!,
    stateHash: sha256(event.state_hash, "case event state hash")!,
    occurredAt: dateTime(event.occurred_at, "case event occurred_at")!,
  };
}

export function parseCaseEventPage(value: unknown): CaseEventPage {
  const page = record(value, "case event page");
  if (!Array.isArray(page.items)) {
    throw new Error("Invalid case response: case event page items must be an array.");
  }
  return {
    items: page.items.map(parseCaseEvent),
    nextCursor: page.next_cursor === null
      ? null
      : stringValue(page.next_cursor, "case event page next_cursor"),
    hasMore: booleanValue(page.has_more, "case event page has_more"),
  };
}

function parseInvocationUsage(value: unknown, field: string): InvocationUsage {
  const usage = record(value, field);
  return {
    turns: integer(usage.turns, `${field}.turns`),
    toolCalls: integer(usage.tool_calls, `${field}.tool_calls`),
    inputTokens: integer(usage.input_tokens, `${field}.input_tokens`),
    outputTokens: integer(usage.output_tokens, `${field}.output_tokens`),
    runtimeSeconds: numberValue(usage.runtime_seconds, `${field}.runtime_seconds`),
    costUsd: numberValue(usage.cost_usd, `${field}.cost_usd`),
  };
}

function parseRunStepState(value: unknown, field: string): RunStepState {
  const step = record(value, field);
  return {
    status: enumValue(step.status, INVOCATION_STATUSES, `${field}.status`),
    attempt: integer(step.attempt, `${field}.attempt`),
    invocationId: uuid(step.invocation_id, `${field}.invocation_id`, true),
    approvalId: uuid(step.approval_id, `${field}.approval_id`, true),
    outputSha256: sha256(step.output_sha256, `${field}.output_sha256`, true),
    usage: parseInvocationUsage(step.usage, `${field}.usage`),
  };
}

function parseAgentInvocation(value: unknown): AgentInvocation {
  const invocation = record(value, "agent invocation");
  return {
    id: uuid(invocation.id, "agent invocation id")!,
    runId: uuid(invocation.run_id, "agent invocation run_id")!,
    caseId: uuid(invocation.case_id, "agent invocation case_id")!,
    planStepId: uuid(invocation.plan_step_id, "agent invocation plan_step_id")!,
    stepKey: stringValue(invocation.step_key, "agent invocation step_key"),
    attempt: integer(invocation.attempt, "agent invocation attempt", 1),
    agentVersionId: uuid(invocation.agent_version_id, "agent invocation agent_version_id", true),
    status: enumValue(invocation.status, INVOCATION_STATUSES, "agent invocation status"),
    outputSchemaRef: stringValue(invocation.output_schema_ref, "agent invocation output schema"),
    inputSha256: sha256(invocation.input_sha256, "agent invocation input hash")!,
    outputSha256: sha256(invocation.output_sha256, "agent invocation output hash", true),
    limits: { ...record(invocation.limits, "agent invocation limits") },
    usage: parseInvocationUsage(invocation.usage, "agent invocation usage"),
    errorCode: stringValue(invocation.error_code, "agent invocation error_code", { nullable: true }),
    startedAt: dateTime(invocation.started_at, "agent invocation started_at", true),
    completedAt: dateTime(invocation.completed_at, "agent invocation completed_at", true),
    createdAt: dateTime(invocation.created_at, "agent invocation created_at")!,
  };
}

export function parseCaseRun(value: unknown): CaseRun {
  const run = record(value, "case run");
  const checkpoint = record(run.checkpoint, "case run checkpoint");
  const workflow = record(checkpoint.workflow_template, "case run workflow template");
  const rawSteps = record(checkpoint.steps, "case run steps");
  if (checkpoint.schema_version !== "pharmaagent-run-state@1.0.0") {
    throw new Error("Invalid case response: unsupported run checkpoint schema.");
  }
  return {
    id: uuid(run.id, "case run id")!,
    caseId: uuid(run.case_id, "case run case_id")!,
    planId: uuid(run.plan_id, "case run plan_id")!,
    planVersion: integer(run.plan_version, "case run plan_version", 1),
    planSha256: sha256(run.plan_sha256, "case run plan hash")!,
    boundStateHash: sha256(run.bound_state_hash, "case run state hash")!,
    status: enumValue(run.status, RUN_STATUSES, "case run status"),
    requestedBy: stringValue(run.requested_by, "case run requested_by"),
    checkpoint: {
      schemaVersion: "pharmaagent-run-state@1.0.0",
      checkpointVersion: integer(checkpoint.checkpoint_version, "checkpoint version", 1),
      stepKey: stringValue(checkpoint.step_key, "checkpoint step_key", { nullable: true }),
      workflowTemplate: {
        id: uuid(workflow.id, "workflow template id")!,
        workflowKey: stringValue(workflow.workflow_key, "workflow template key"),
        version: stringValue(workflow.version, "workflow template version"),
        manifestSha256: sha256(workflow.manifest_sha256, "workflow template hash")!,
      },
      steps: Object.fromEntries(
        Object.entries(rawSteps).map(([key, step]) => [key, parseRunStepState(step, `run step ${key}`)]),
      ),
      budget: parseInvocationUsage(checkpoint.budget, "case run budget"),
      pauseRequested: booleanValue(checkpoint.pause_requested, "checkpoint pause_requested"),
      cancelRequested: booleanValue(checkpoint.cancel_requested, "checkpoint cancel_requested"),
    },
    activeInvocation: run.active_invocation === null
      ? null
      : parseAgentInvocation(run.active_invocation),
    errorCode: stringValue(run.error_code, "case run error_code", { nullable: true }),
    startedAt: dateTime(run.started_at, "case run started_at", true),
    completedAt: dateTime(run.completed_at, "case run completed_at", true),
    createdAt: dateTime(run.created_at, "case run created_at")!,
  };
}

function parseRunEvent(value: unknown): RunEvent {
  const event = record(value, "run event");
  return {
    id: uuid(event.id, "run event id")!,
    runId: uuid(event.run_id, "run event run_id")!,
    caseId: uuid(event.case_id, "run event case_id")!,
    sequence: integer(event.sequence, "run event sequence", 1),
    eventType: stringValue(event.event_type, "run event type"),
    actorType: stringValue(event.actor_type, "run event actor_type"),
    actorId: stringValue(event.actor_id, "run event actor_id"),
    requestId: stringValue(event.request_id, "run event request_id"),
    payload: { ...record(event.payload, "run event payload") },
    previousEventHash: sha256(event.previous_event_hash, "run event previous hash", true),
    eventHash: sha256(event.event_hash, "run event hash")!,
    occurredAt: dateTime(event.occurred_at, "run event occurred_at")!,
  };
}

export function parseRunEventPage(value: unknown): RunEventPage {
  const page = record(value, "run event page");
  if (!Array.isArray(page.items)) {
    throw new Error("Invalid case response: run event page items must be an array.");
  }
  return {
    items: page.items.map(parseRunEvent),
    nextCursor: page.next_cursor === null
      ? null
      : stringValue(page.next_cursor, "run event page next_cursor"),
    hasMore: booleanValue(page.has_more, "run event page has_more"),
  };
}

function parseEvidenceReference(value: unknown, field: string): EvidenceReference {
  const evidence = record(value, field);
  return {
    sourceType: enumValue(
      evidence.source_type,
      ["EXTERNAL_REGULATORY", "INTERNAL_ASSET"] as const,
      `${field}.source_type`,
    ),
    sourceVersionId: uuid(evidence.source_version_id, `${field}.source_version_id`)! ,
    sourceHash: sha256(evidence.source_hash, `${field}.source_hash`)! ,
    anchorId: stringValue(evidence.anchor_id, `${field}.anchor_id`),
    excerpt: stringValue(evidence.excerpt, `${field}.excerpt`),
    sourceUrl: stringValue(evidence.source_url, `${field}.source_url`, { nullable: true }),
  };
}

function parseImpactHypothesis(value: unknown): ImpactHypothesis {
  const item = record(value, "impact hypothesis");
  if (!Array.isArray(item.external_evidence) || !Array.isArray(item.internal_evidence)) {
    throw new Error("Invalid case response: impact evidence must be arrays.");
  }
  if (item.decision_support_only !== true) {
    throw new Error("Invalid case response: impact output crossed its decision-support boundary.");
  }
  return {
    id: uuid(item.id, "impact hypothesis id")!,
    caseId: uuid(item.case_id, "impact hypothesis case_id")!,
    runId: uuid(item.run_id, "impact hypothesis run_id", true),
    findingId: stringValue(item.finding_id, "impact hypothesis finding_id"),
    assetId: uuid(item.asset_id, "impact hypothesis asset_id")!,
    assetVersionId: uuid(item.asset_version_id, "impact hypothesis asset_version_id")!,
    assetKey: stringValue(item.asset_key, "impact hypothesis asset_key"),
    assetTitle: stringValue(item.asset_title, "impact hypothesis asset_title"),
    assetType: stringValue(item.asset_type, "impact hypothesis asset_type"),
    assetDomain: stringValue(item.asset_domain, "impact hypothesis asset_domain"),
    revision: integer(item.revision, "impact hypothesis revision", 1),
    effectiveStatus: stringValue(item.effective_status, "impact hypothesis effective_status"),
    relationshipType: stringValue(item.relationship_type, "impact hypothesis relationship_type"),
    statement: stringValue(item.statement, "impact hypothesis statement"),
    knownFacts: stringArray(item.known_facts, "impact hypothesis known_facts"),
    derivedRelationships: stringArray(item.derived_relationships, "impact hypothesis derived_relationships"),
    assumptions: stringArray(item.assumptions, "impact hypothesis assumptions"),
    counterevidence: stringArray(item.counterevidence, "impact hypothesis counterevidence"),
    unknowns: stringArray(item.unknowns, "impact hypothesis unknowns"),
    recommendedVerification: stringArray(
      item.recommended_verification,
      "impact hypothesis recommended_verification",
    ),
    externalEvidence: item.external_evidence.map((entry, index) => (
      parseEvidenceReference(entry, `external evidence ${index}`)
    )),
    internalEvidence: item.internal_evidence.map((entry, index) => (
      parseEvidenceReference(entry, `internal evidence ${index}`)
    )),
    confidence: numberValue(item.confidence, "impact hypothesis confidence"),
    reviewPriority: stringValue(item.review_priority, "impact hypothesis review_priority"),
    status: enumValue(
      item.status,
      ["PROPOSED", "ACCEPTED", "REJECTED"] as const,
      "impact hypothesis status",
    ),
    hypothesisSha256: sha256(item.hypothesis_sha256, "impact hypothesis SHA-256")!,
    createdBy: stringValue(item.created_by, "impact hypothesis created_by"),
    reviewedBy: stringValue(item.reviewed_by, "impact hypothesis reviewed_by", { nullable: true }),
    reviewReason: stringValue(item.review_reason, "impact hypothesis review_reason", { nullable: true }),
    reviewedAt: dateTime(item.reviewed_at, "impact hypothesis reviewed_at", true),
    createdAt: dateTime(item.created_at, "impact hypothesis created_at")!,
    decisionSupportOnly: true,
  };
}

export function parseImpactMap(value: unknown): ImpactMap {
  const map = record(value, "impact map");
  if (!Array.isArray(map.items)) {
    throw new Error("Invalid case response: impact map items must be an array.");
  }
  return {
    caseId: uuid(map.case_id, "impact map case_id")!,
    generatedCount: integer(map.generated_count, "impact map generated_count"),
    items: map.items.map(parseImpactHypothesis),
    notice: stringValue(map.notice, "impact map notice"),
  };
}

export function parseVerificationReport(value: unknown): VerificationReport | null {
  if (value === null) return null;
  const report = record(value, "verification report");
  if (!Array.isArray(report.checks) || !Array.isArray(report.issues)) {
    throw new Error("Invalid case response: verification checks and issues must be arrays.");
  }
  if (report.independent_context !== true) {
    throw new Error("Invalid case response: verification must use an independent context.");
  }
  return {
    id: uuid(report.id, "verification report id")!,
    caseId: uuid(report.case_id, "verification case id")!,
    planId: uuid(report.plan_id, "verification plan id")!,
    correctionIteration: integer(report.correction_iteration, "verification iteration"),
    status: enumValue(report.status, ["PASS", "REVISE", "BLOCK"] as const, "verification status"),
    checks: report.checks.map((entry, index) => {
      const check = record(entry, `verification check ${index}`);
      return {
        check: stringValue(check.check, `verification check ${index}.check`),
        status: enumValue(check.status, ["PASS", "FAIL"] as const, `verification check ${index}.status`),
        detail: stringValue(check.detail, `verification check ${index}.detail`),
      };
    }),
    issues: report.issues.map((entry, index) => {
      const issue = record(entry, `verification issue ${index}`);
      return {
        severity: enumValue(issue.severity, ["CRITICAL", "MAJOR", "MINOR"] as const, `verification issue ${index}.severity`),
        code: stringValue(issue.code, `verification issue ${index}.code`),
        affectedClaim: stringValue(issue.affected_claim, `verification issue ${index}.affected_claim`),
        reason: stringValue(issue.reason, `verification issue ${index}.reason`),
        supportingEvidence: stringArray(issue.supporting_evidence, `verification issue ${index}.supporting_evidence`),
        requiredCorrection: stringValue(issue.required_correction, `verification issue ${index}.required_correction`),
        responsibleAgent: stringValue(issue.responsible_agent, `verification issue ${index}.responsible_agent`),
      };
    }),
    verifiedHypothesisIds: stringArray(report.verified_hypothesis_ids, "verification hypothesis ids"),
    reportSha256: sha256(report.report_sha256, "verification report hash")!,
    inputSha256: sha256(report.input_sha256, "verification input hash")!,
    verifier: `${stringValue(report.verifier_name, "verification agent")}@${stringValue(report.verifier_version, "verification agent version")}`,
    createdAt: dateTime(report.created_at, "verification created_at")!,
    independentContext: true,
  };
}

function parseArtifactVersion(value: unknown): ArtifactVersion {
  const item = record(value, "artifact version");
  if (!Array.isArray(item.evidence)) {
    throw new Error("Invalid case response: artifact evidence must be an array.");
  }
  const approval = record(item.approval, "artifact approval");
  return {
    id: uuid(item.id, "artifact version id")!,
    artifactId: uuid(item.artifact_id, "artifact id")!,
    title: stringValue(item.title, "artifact title"),
    version: integer(item.version, "artifact version", 1),
    verificationReportId: uuid(item.verification_report_id, "artifact verification report id")!,
    content: { ...record(item.content, "artifact content") },
    contentSha256: sha256(item.content_sha256, "artifact content hash")!,
    evidenceManifestSha256: sha256(item.evidence_manifest_sha256, "artifact evidence hash")!,
    status: enumValue(item.status, ["DRAFT", "APPROVED", "REJECTED"] as const, "artifact status"),
    createdAt: dateTime(item.created_at, "artifact created_at")!,
    evidence: item.evidence.map((entry, index) => {
      const evidence = record(entry, `artifact evidence ${index}`);
      return {
        id: uuid(evidence.id, `artifact evidence ${index}.id`)!,
        anchor: stringValue(evidence.anchor, `artifact evidence ${index}.anchor`),
        sourceSha256: sha256(evidence.source_sha256, `artifact evidence ${index}.source hash`)!,
        excerptSha256: sha256(evidence.excerpt_sha256, `artifact evidence ${index}.excerpt hash`)!,
        evidenceRole: stringValue(evidence.evidence_role, `artifact evidence ${index}.role`),
      };
    }),
    approval: {
      id: uuid(approval.id, "artifact approval id")!,
      status: enumValue(approval.status, ["PENDING", "APPROVED", "REJECTED", "CANCELLED", "EXPIRED"] as const, "artifact approval status"),
      requestedBy: stringValue(approval.requested_by, "artifact approval requester"),
      assignedReviewerId: stringValue(approval.assigned_reviewer_id, "artifact assigned reviewer", { nullable: true }),
      decisionBy: stringValue(approval.decision_by, "artifact decision identity", { nullable: true }),
      decisionReason: stringValue(approval.decision_reason, "artifact decision reason", { nullable: true }),
    },
  };
}

export function parseArtifactPage(value: unknown): ArtifactPage {
  const page = record(value, "artifact page");
  if (!Array.isArray(page.items)) {
    throw new Error("Invalid case response: artifact page items must be an array.");
  }
  return { items: page.items.map(parseArtifactVersion) };
}

export function parseSingleArtifact(value: unknown): ArtifactVersion {
  return parseArtifactVersion(value);
}

function parseIntegrationDraft(value: unknown): IntegrationDraft {
  const item = record(value, "integration draft");
  const content = record(item.content, "integration draft content");
  if (item.external_delivery_allowed !== false) {
    throw new Error("Invalid case response: integration draft crossed its no-delivery boundary.");
  }
  if (content.decision_support_only !== true || content.manual_delivery_required !== true) {
    throw new Error("Invalid case response: integration draft is missing its manual-use controls.");
  }
  return {
    id: uuid(item.id, "integration draft id")!,
    caseId: uuid(item.case_id, "integration draft case id")!,
    runId: uuid(item.run_id, "integration draft run id", true),
    channel: enumValue(
      item.channel,
      ["INTERNAL", "EMAIL", "SLACK", "TEAMS", "NOTION", "TASK"] as const,
      "integration draft channel",
    ),
    action: enumValue(item.action, ["CREATE_DRAFT"] as const, "integration draft action"),
    destination: stringValue(item.destination, "integration draft destination"),
    content: {
      title: stringValue(content.title, "integration draft title"),
      body: stringValue(content.body, "integration draft body"),
      decision_support_only: true,
      manual_delivery_required: true,
    },
    contentSha256: sha256(item.content_sha256, "integration draft content hash")!,
    status: enumValue(
      item.status,
      ["DRAFT", "REVIEWED_FOR_MANUAL_USE", "CANCELLED"] as const,
      "integration draft status",
    ),
    externalDeliveryAllowed: false,
    requestedBy: stringValue(item.requested_by, "integration draft requester"),
    reviewedBy: stringValue(item.reviewed_by, "integration draft reviewer", { nullable: true }),
    reviewReason: stringValue(item.review_reason, "integration draft review reason", { nullable: true }),
    reviewedAt: dateTime(item.reviewed_at, "integration draft reviewed_at", true),
    createdAt: dateTime(item.created_at, "integration draft created_at")!,
  };
}

export function parseIntegrationDraftPage(value: unknown): IntegrationDraftPage {
  const page = record(value, "integration draft page");
  if (!Array.isArray(page.items)) {
    throw new Error("Invalid case response: integration draft page items must be an array.");
  }
  return { items: page.items.map(parseIntegrationDraft) };
}

export function parseSingleIntegrationDraft(value: unknown): IntegrationDraft {
  return parseIntegrationDraft(value);
}

export function latestPlanVersion(events: readonly CaseEvent[]): number | undefined {
  const versions = events.flatMap((event) => {
    if (event.eventType !== "PLAN_GENERATED") return [];
    const version = event.payload.plan_version;
    return typeof version === "number" && Number.isInteger(version) && version > 0 ? [version] : [];
  });
  return versions.length ? Math.max(...versions) : undefined;
}

export function latestRunId(events: readonly CaseEvent[]): string | undefined {
  return events.toReversed().find((event) => (
    event.eventType === "RUN_STARTED" && typeof event.payload.run_id === "string"
  ))?.payload.run_id as string | undefined;
}

export function isPlanBindingCurrent(plan: CasePlan, agentCase: AgentCase): boolean {
  return plan.planSha256 === plan.approval.planSha256
    && plan.basedOnStateHash === plan.approval.boundStateHash
    && plan.basedOnStateHash === agentCase.currentStateHash;
}

export function formatCaseStatus(
  status: CaseStatus | ApprovalStatus | AgentRunStatus | InvocationStatus,
): string {
  return status
    .toLocaleLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toLocaleUpperCase() + part.slice(1))
    .join(" ");
}

export function caseStatusTone(status: CaseStatus): CaseStatusTone {
  if (["FAILED", "CANCELLED", "STALE"].includes(status)) return "danger";
  if (["AWAITING_PLAN_APPROVAL", "WAITING_FOR_INPUT", "WAITING_FOR_REVIEW", "NEEDS_REVISION"].includes(status)) {
    return "attention";
  }
  if (status === "READY") return "ready";
  if (["PLANNING", "RUNNING"].includes(status)) return "active";
  if (status === "COMPLETED") return "closed";
  return "neutral";
}

export function shortHash(hash: string, edge = 8): string {
  if (hash.length <= edge * 2 + 1) return hash;
  return `${hash.slice(0, edge)}\u2026${hash.slice(-edge)}`;
}

export function isCaseWorkspaceView(value: string | string[] | undefined): value is CaseWorkspaceView {
  return typeof value === "string"
    && ["overview", "plan", "execution", "impact", "review", "integrations", "evidence", "history"].includes(value);
}

export function isUuid(value: string): boolean {
  return UUID_PATTERN.test(value);
}
