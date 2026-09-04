import "server-only";

import { getBackendBearerAssertion } from "@/lib/backend-auth";

export type InventoryItem = {
  id: string;
  kind: "AGENT_VERSION" | "SKILL_VERSION" | "TOOL_VERSION" | "WORKFLOW_VERSION";
  key: string;
  version: string;
  sha256: string;
  releaseStatus: string;
};

export type EvaluationSuite = {
  id: string;
  suiteKey: string;
  version: string;
  name: string;
  targetKind: "AGENT_VERSION" | "WORKFLOW_VERSION";
  suiteSha256: string;
  caseCount: number;
};

export type EvaluationRun = {
  id: string;
  suiteId: string;
  targetKind: "AGENT_VERSION" | "WORKFLOW_VERSION";
  targetVersionId: string;
  targetSha256: string;
  status: "PENDING" | "RUNNING" | "PASSED" | "FAILED";
  metrics: Record<string, unknown>;
  totalTrials: number;
  passedTrials: number;
  criticalFailures: number;
  totalCostUsd: number;
  totalLatencyMs: number;
  trials: Array<{ id: string; status: "PASSED" | "FAILED"; trajectory: Array<Record<string, unknown>> }>;
};

export type ControlTower = {
  inventory: Record<string, number>;
  operationalHealth: Record<string, number>;
  quality: Record<string, number>;
  security: Record<string, number>;
  costPerformance: Record<string, number>;
  businessValue: Record<string, number>;
  generatedAt: string;
};

export type RuntimeControl = {
  id: string;
  controlKey: string;
  scope: "GLOBAL" | "AGENT";
  agentVersionId?: string;
  suspended: boolean;
  reason: string;
  revision: number;
  updatedBy: string;
  updatedAt: string;
};

export type ApprovalCenterItem = {
  id: string;
  caseId: string;
  caseTitle: string;
  planId: string;
  planVersion: number;
  planSha256: string;
  boundStateHash: string;
  runId?: string;
  stepKey?: string;
  artifactVersionId?: string;
  approvalType: "PLAN_APPROVAL" | "STEP_APPROVAL" | "ARTIFACT_APPROVAL";
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED" | "EXPIRED";
  requestedBy: string;
  assignedReviewerId?: string;
  decisionBy?: string;
  decisionReason?: string;
  expiresAt: string;
  expired: boolean;
  createdAt: string;
};

export class GovernanceApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "GovernanceApiError";
  }
}

const API_BASE_URL = process.env.API_BASE_URL?.replace(/\/$/, "");

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new GovernanceApiError(502, `Invalid governance response: ${label}.`);
  }
  return value as Record<string, unknown>;
}

function stringValue(value: unknown, label: string): string {
  if (typeof value !== "string" || !value) throw new GovernanceApiError(502, `Invalid ${label}.`);
  return value;
}

function numberValue(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new GovernanceApiError(502, `Invalid ${label}.`);
  return value;
}

async function request(path: string, init: RequestInit = {}): Promise<unknown> {
  if (!API_BASE_URL) throw new GovernanceApiError(0, "API_BASE_URL is not configured.");
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${await getBackendBearerAssertion()}`);
  if (init.body) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    throw new GovernanceApiError(0, "The governance service could not be reached.");
  }
  if (!response.ok) {
    let detail = "The governance operation was rejected.";
    try {
      const problem = record(await response.json(), "problem");
      if (typeof problem.detail === "string") detail = problem.detail;
    } catch {
      // Keep the bounded fallback message.
    }
    throw new GovernanceApiError(response.status, detail);
  }
  return response.json() as Promise<unknown>;
}

function parseSuite(value: unknown): EvaluationSuite {
  const item = record(value, "suite");
  const cases = Array.isArray(item.cases) ? item.cases : [];
  return {
    id: stringValue(item.id, "suite id"),
    suiteKey: stringValue(item.suite_key, "suite key"),
    version: stringValue(item.version, "suite version"),
    name: stringValue(item.name, "suite name"),
    targetKind: stringValue(item.target_kind, "suite target kind") as EvaluationSuite["targetKind"],
    suiteSha256: stringValue(item.suite_sha256, "suite hash"),
    caseCount: cases.length,
  };
}

function parseRun(value: unknown): EvaluationRun {
  const item = record(value, "evaluation run");
  const rawTrials = Array.isArray(item.trials) ? item.trials : [];
  return {
    id: stringValue(item.id, "evaluation run id"),
    suiteId: stringValue(item.suite_id, "evaluation suite id"),
    targetKind: stringValue(item.target_kind, "evaluation target kind") as EvaluationRun["targetKind"],
    targetVersionId: stringValue(item.target_version_id, "evaluation target id"),
    targetSha256: stringValue(item.target_sha256, "evaluation target hash"),
    status: stringValue(item.status, "evaluation status") as EvaluationRun["status"],
    metrics: { ...record(item.metrics, "evaluation metrics") },
    totalTrials: numberValue(item.total_trials, "total trials"),
    passedTrials: numberValue(item.passed_trials, "passed trials"),
    criticalFailures: numberValue(item.critical_failures, "critical failures"),
    totalCostUsd: numberValue(item.total_cost_usd, "total cost"),
    totalLatencyMs: numberValue(item.total_latency_ms, "total latency"),
    trials: rawTrials.map((raw) => {
      const trial = record(raw, "evaluation trial");
      return {
        id: stringValue(trial.id, "trial id"),
        status: stringValue(trial.status, "trial status") as "PASSED" | "FAILED",
        trajectory: (Array.isArray(trial.trajectory) ? trial.trajectory : []).map((entry) => record(entry, "trajectory event")),
      };
    }),
  };
}

export async function listGovernanceInventory(): Promise<InventoryItem[]> {
  const page = record(await request("/api/v1/control-tower/inventory"), "inventory");
  if (!Array.isArray(page.items)) throw new GovernanceApiError(502, "Invalid inventory items.");
  return page.items.map((raw) => {
    const item = record(raw, "inventory item");
    return {
      id: stringValue(item.id, "inventory id"),
      kind: stringValue(item.kind, "inventory kind") as InventoryItem["kind"],
      key: stringValue(item.key, "inventory key"),
      version: stringValue(item.version, "inventory version"),
      sha256: stringValue(item.sha256, "inventory hash"),
      releaseStatus: stringValue(item.release_status, "inventory status"),
    };
  });
}

export async function listEvaluationSuites(): Promise<EvaluationSuite[]> {
  const page = record(await request("/api/v1/eval-suites"), "evaluation suites");
  return (Array.isArray(page.items) ? page.items : []).map(parseSuite);
}

export async function listEvaluationRuns(): Promise<EvaluationRun[]> {
  const page = record(await request("/api/v1/eval-runs"), "evaluation runs");
  return (Array.isArray(page.items) ? page.items : []).map(parseRun);
}

export async function createEvaluationSuite(payload: Record<string, unknown>, idempotencyKey: string): Promise<EvaluationSuite> {
  return parseSuite(await request("/api/v1/eval-suites", { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(payload) }));
}

export async function createEvaluationRun(payload: Record<string, unknown>, idempotencyKey: string): Promise<EvaluationRun> {
  return parseRun(await request("/api/v1/eval-runs", { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(payload) }));
}

export async function approveEvaluationRelease(runId: string, payload: Record<string, unknown>, idempotencyKey: string): Promise<void> {
  await request(`/api/v1/eval-runs/${encodeURIComponent(runId)}/approve-release`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(payload) });
}

export async function getControlTower(): Promise<ControlTower> {
  const item = record(await request("/api/v1/control-tower/summary"), "control tower");
  const numericMap = (value: unknown, label: string) => Object.fromEntries(Object.entries(record(value, label)).map(([key, raw]) => [key, numberValue(raw, `${label}.${key}`)]));
  return {
    inventory: numericMap(item.inventory, "inventory"),
    operationalHealth: numericMap(item.operational_health, "operational health"),
    quality: numericMap(item.quality, "quality"),
    security: numericMap(item.security, "security"),
    costPerformance: numericMap(item.cost_performance, "cost performance"),
    businessValue: numericMap(item.business_value, "business value"),
    generatedAt: stringValue(item.generated_at, "generated time"),
  };
}

function parseRuntimeControl(value: unknown): RuntimeControl {
  const item = record(value, "runtime control");
  return {
    id: stringValue(item.id, "runtime control id"),
    controlKey: stringValue(item.control_key, "runtime control key"),
    scope: stringValue(item.scope, "runtime control scope") as RuntimeControl["scope"],
    agentVersionId: typeof item.agent_version_id === "string" ? item.agent_version_id : undefined,
    suspended: Boolean(item.suspended),
    reason: stringValue(item.reason, "runtime control reason"),
    revision: numberValue(item.revision, "runtime control revision"),
    updatedBy: stringValue(item.updated_by, "runtime control actor"),
    updatedAt: stringValue(item.updated_at, "runtime control time"),
  };
}

export async function listRuntimeControls(): Promise<RuntimeControl[]> {
  const page = record(await request("/api/v1/control-tower/controls"), "runtime controls");
  return (Array.isArray(page.items) ? page.items : []).map(parseRuntimeControl);
}

export async function updateRuntimeControl(
  target: "global" | `agents/${string}`,
  payload: { suspended: boolean; reason: string; expected_revision?: number },
): Promise<RuntimeControl> {
  return parseRuntimeControl(await request(`/api/v1/control-tower/controls/${target}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  }));
}

function parseApproval(value: unknown): ApprovalCenterItem {
  const item = record(value, "approval center item");
  const optionalString = (candidate: unknown) => typeof candidate === "string" ? candidate : undefined;
  return {
    id: stringValue(item.id, "approval id"),
    caseId: stringValue(item.case_id, "approval case id"),
    caseTitle: stringValue(item.case_title, "approval case title"),
    planId: stringValue(item.plan_id, "approval plan id"),
    planVersion: numberValue(item.plan_version, "approval plan version"),
    planSha256: stringValue(item.plan_sha256, "approval plan hash"),
    boundStateHash: stringValue(item.bound_state_hash, "approval state hash"),
    runId: optionalString(item.run_id),
    stepKey: optionalString(item.step_key),
    artifactVersionId: optionalString(item.artifact_version_id),
    approvalType: stringValue(item.approval_type, "approval type") as ApprovalCenterItem["approvalType"],
    status: stringValue(item.status, "approval status") as ApprovalCenterItem["status"],
    requestedBy: stringValue(item.requested_by, "approval requester"),
    assignedReviewerId: optionalString(item.assigned_reviewer_id),
    decisionBy: optionalString(item.decision_by),
    decisionReason: optionalString(item.decision_reason),
    expiresAt: stringValue(item.expires_at, "approval expiry"),
    expired: Boolean(item.expired),
    createdAt: stringValue(item.created_at, "approval creation time"),
  };
}

export async function listApprovals(
  status?: ApprovalCenterItem["status"],
): Promise<ApprovalCenterItem[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const page = record(await request(`/api/v1/approvals${query}`), "approval center");
  return (Array.isArray(page.items) ? page.items : []).map(parseApproval);
}
