"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  CaseApiError,
  controlAgentCaseRun,
  composeAgentCaseArtifact,
  createAgentCaseIntegrationDraft,
  createAgentCase,
  createAgentCasePlan,
  decideAgentCaseArtifact,
  decideAgentCaseImpact,
  decideAgentCasePlan,
  decideAgentRunStep,
  generateAgentCaseImpact,
  reviewAgentCaseIntegrationDraft,
  startAgentCaseRun,
  verifyAgentCase,
  type CasePlanStepInput,
} from "@/lib/case-api-client";
import { getPortalIdentity } from "@/lib/backend-auth";
import { isUuid, type CaseActionState } from "@/lib/case-types";

const SHA256_PATTERN = /^[a-f0-9]{64}$/;

function formString(formData: FormData, name: string, maximum: number): string {
  const value = formData.get(name);
  if (typeof value !== "string") return "";
  return value.trim().slice(0, maximum);
}

function actionError(error: unknown): CaseActionState {
  if (!(error instanceof CaseApiError)) {
    return { status: "error", message: "The case operation could not be completed." };
  }

  const messages: Record<number, string> = {
    0: error.message,
    403: "Your authenticated account does not have the required governed-case role.",
    404: "The selected case or exact source version is not available in the admitted Drug corpus.",
    409: "The case changed before this operation completed. Reload the record and verify the current hashes.",
    422: "The case service rejected one or more controlled fields. Verify the identifiers and plan input.",
  };
  return {
    status: "error",
    message: messages[error.status] ?? "The governed case service rejected the operation.",
    requestId: error.requestId,
  };
}

function roleSet(roles: readonly string[]) {
  return new Set(roles);
}

function planSteps(domainLens: string): CasePlanStepInput[] {
  const lens = domainLens || "cross-functional pharmaceutical quality systems";
  return [
    {
      stepKey: "regulatory_evidence",
      title: "Extract version-bound regulatory findings",
      instructions: `Read only the pinned FDA source version. Extract bounded findings relevant to ${lens}; every material statement must retain an exact source anchor.`,
      dependsOn: [],
      outputSchemaRef: "urn:pharma-agent-os:output:regulatory-finding:v1",
      riskLevel: "R0",
      limits: { maxTurns: 4, maxToolCalls: 12, maxRuntimeSeconds: 180, maxCostUsd: 2 },
    },
    {
      stepKey: "internal_relevance",
      title: "Identify internal evidence candidates",
      instructions: `Search only case-authorized internal knowledge for assets potentially relevant to ${lens}. Keep candidates separate from approved organizational facts.`,
      dependsOn: ["regulatory_evidence"],
      outputSchemaRef: "urn:pharma-agent-os:output:internal-asset-candidate:v1",
      riskLevel: "R1",
      limits: { maxTurns: 5, maxToolCalls: 12, maxRuntimeSeconds: 240, maxCostUsd: 2 },
    },
    {
      stepKey: "impact_hypotheses",
      title: "Draft potential impact hypotheses",
      instructions: "Relate supported regulatory findings to authorized internal evidence. Label facts, hypotheses, assumptions, and unknowns; do not make a compliance determination.",
      dependsOn: ["regulatory_evidence", "internal_relevance"],
      outputSchemaRef: "urn:pharma-agent-os:output:impact-hypothesis:v1",
      riskLevel: "R2",
      requiresApproval: true,
      limits: { maxTurns: 6, maxToolCalls: 4, maxRuntimeSeconds: 240, maxCostUsd: 3 },
    },
    {
      stepKey: "independent_verification",
      title: "Challenge support and boundaries",
      instructions: "Independently verify citation validity, claim support, relationship strength, and prohibited-action boundaries. Return unresolved questions instead of filling evidence gaps.",
      dependsOn: ["impact_hypotheses"],
      outputSchemaRef: "urn:pharma-agent-os:output:verification-report:v1",
      riskLevel: "R1",
      limits: { maxTurns: 5, maxToolCalls: 8, maxRuntimeSeconds: 240, maxCostUsd: 3 },
    },
  ];
}

export async function createCaseAction(
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  if (!roles.has("analyst") && !roles.has("system_owner")) {
    return actionError(new CaseApiError(403, "Case creation is restricted."));
  }

  const title = formString(formData, "title", 300);
  const objective = formString(formData, "objective", 4_000);
  const warningLetterId = formString(formData, "warning_letter_id", 64);
  const documentVersionId = formString(formData, "document_version_id", 64);
  const intentId = formString(formData, "intent_id", 64);

  if (!title || !objective) {
    return { status: "error", message: "A case title and a specific review objective are required." };
  }
  if (!isUuid(warningLetterId) || !isUuid(documentVersionId)) {
    return { status: "error", message: "Warning-letter and document-version identifiers must be UUIDs." };
  }
  if (!isUuid(intentId)) {
    return { status: "error", message: "This form expired. Reload the page and try again." };
  }

  let createdCase;
  try {
    createdCase = await createAgentCase(
      {
        title,
        objective,
        workflowKey: "regulatory-impact-review",
        warningLetterId,
        documentVersionId,
      },
      `case-create:${intentId}`,
    );
  } catch (error) {
    return actionError(error);
  }

  revalidatePath("/cases");
  redirect(`/cases/${createdCase.id}`);
}

export async function createPlanAction(
  caseId: string,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  if (!roles.has("analyst") && !roles.has("system_owner")) {
    return actionError(new CaseApiError(403, "Plan creation is restricted."));
  }
  if (!isUuid(caseId)) {
    return { status: "error", message: "The case identifier is invalid." };
  }

  const intentId = formString(formData, "intent_id", 64);
  const domainLens = formString(formData, "domain_lens", 300);
  const assignedReviewerId = formString(formData, "assigned_reviewer_id", 255);
  if (!isUuid(intentId)) {
    return { status: "error", message: "This form expired. Reload the page and try again." };
  }

  try {
    await createAgentCasePlan(
      caseId,
      {
        steps: planSteps(domainLens),
        assignedReviewerId: assignedReviewerId || undefined,
      },
      `plan-create:${intentId}`,
    );
  } catch (error) {
    return actionError(error);
  }

  revalidatePath(`/cases/${caseId}`);
  return { status: "success", message: "A new immutable plan version is awaiting independent review." };
}

export async function decidePlanAction(
  caseId: string,
  version: number,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  if (!roleSet(identity.roles).has("reviewer")) {
    return actionError(new CaseApiError(403, "Plan decisions require the QA Reviewer role."));
  }
  if (!isUuid(caseId) || !Number.isInteger(version) || version < 1) {
    return { status: "error", message: "The case plan reference is invalid." };
  }

  const decision = formString(formData, "decision", 16);
  const reason = formString(formData, "reason", 2_000);
  const expectedPlanSha256 = formString(formData, "expected_plan_sha256", 64);
  const expectedStateHash = formString(formData, "expected_state_hash", 64);
  const intentId = formString(formData, "intent_id", 64);

  if (decision !== "approve" && decision !== "reject") {
    return { status: "error", message: "Choose approve or reject." };
  }
  if (reason.length < 8) {
    return { status: "error", message: "Provide a specific review reason of at least 8 characters." };
  }
  if (!SHA256_PATTERN.test(expectedPlanSha256) || !SHA256_PATTERN.test(expectedStateHash)) {
    return { status: "error", message: "The approval binding is invalid. Reload the case before deciding." };
  }
  if (!isUuid(intentId)) {
    return { status: "error", message: "This decision form expired. Reload the case and try again." };
  }

  try {
    await decideAgentCasePlan(
      caseId,
      version,
      {
        decision,
        expectedPlanSha256,
        expectedStateHash,
        reason,
      },
      `plan-decision:${intentId}`,
    );
  } catch (error) {
    if (error instanceof CaseApiError && error.status === 409) {
      revalidatePath("/cases");
      revalidatePath(`/cases/${caseId}`);
    }
    return actionError(error);
  }

  revalidatePath("/cases");
  revalidatePath(`/cases/${caseId}`);
  return {
    status: "success",
    message: decision === "approve"
      ? "Plan approved against the displayed plan and state hashes."
      : "Plan rejected. The case now requires a new plan version.",
  };
}

export async function startRunAction(
  caseId: string,
  planVersion: number,
  planSha256: string,
  stateHash: string,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  if (!roles.has("analyst") && !roles.has("system_owner")) {
    return actionError(new CaseApiError(403, "Run start is restricted."));
  }
  const intentId = formString(formData, "intent_id", 64);
  if (
    !isUuid(caseId)
    || !isUuid(intentId)
    || !Number.isInteger(planVersion)
    || planVersion < 1
    || !SHA256_PATTERN.test(planSha256)
    || !SHA256_PATTERN.test(stateHash)
  ) {
    return { status: "error", message: "The approved run binding is invalid. Reload the case." };
  }
  try {
    await startAgentCaseRun(
      caseId,
      { version: planVersion, planSha256, basedOnStateHash: stateHash },
      `run-start:${intentId}`,
    );
  } catch (error) {
    return actionError(error);
  }
  revalidatePath("/cases");
  revalidatePath(`/cases/${caseId}`);
  return { status: "success", message: "Run started and queued at its first durable boundary." };
}

export async function controlRunAction(
  caseId: string,
  runId: string,
  operation: "pause" | "resume" | "cancel",
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  if (!roles.has("analyst") && !roles.has("system_owner")) {
    return actionError(new CaseApiError(403, "Run control is restricted."));
  }
  const intentId = formString(formData, "intent_id", 64);
  const reason = formString(formData, "reason", 2_000);
  if (!isUuid(caseId) || !isUuid(runId) || !isUuid(intentId) || reason.length < 8) {
    return { status: "error", message: "Provide a specific control reason of at least 8 characters." };
  }
  try {
    await controlAgentCaseRun(runId, operation, reason, `run-${operation}:${intentId}`);
  } catch (error) {
    return actionError(error);
  }
  revalidatePath("/cases");
  revalidatePath(`/cases/${caseId}`);
  return {
    status: "success",
    message: `Run ${operation === "cancel" ? "cancelled" : `${operation}d`} at a persisted boundary.`,
  };
}

export async function decideRunStepAction(
  caseId: string,
  runId: string,
  stepKey: string,
  approvalId: string,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  if (!roleSet(identity.roles).has("reviewer")) {
    return actionError(new CaseApiError(403, "Step decisions require the QA Reviewer role."));
  }
  const intentId = formString(formData, "intent_id", 64);
  const decision = formString(formData, "decision", 16);
  const reason = formString(formData, "reason", 2_000);
  if (
    !isUuid(caseId)
    || !isUuid(runId)
    || !isUuid(approvalId)
    || !isUuid(intentId)
    || !/^[a-z][a-z0-9_]{1,63}$/.test(stepKey)
    || (decision !== "approve" && decision !== "reject")
    || reason.length < 8
  ) {
    return { status: "error", message: "The step decision is incomplete or stale." };
  }
  try {
    await decideAgentRunStep(
      runId,
      stepKey,
      { decision, approvalId, reason },
      `step-decision:${intentId}`,
    );
  } catch (error) {
    return actionError(error);
  }
  revalidatePath(`/cases/${caseId}`);
  return {
    status: "success",
    message: decision === "approve" ? "Step execution approved." : "Step execution rejected.",
  };
}

export async function generateImpactAction(
  caseId: string,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  if (!roles.has("analyst") && !roles.has("system_owner")) {
    return actionError(new CaseApiError(403, "Impact generation is restricted."));
  }
  const intentId = formString(formData, "intent_id", 64);
  const query = formString(formData, "query", 500);
  if (!isUuid(caseId) || !isUuid(intentId)) {
    return { status: "error", message: "This impact request expired. Reload the case." };
  }
  try {
    await generateAgentCaseImpact(
      caseId,
      { query: query || undefined, perFindingLimit: 5 },
      `impact-generate:${intentId}`,
    );
  } catch (error) {
    return actionError(error);
  }
  revalidatePath(`/cases/${caseId}`);
  return {
    status: "success",
    message: "Evidence-linked hypotheses were generated for independent human review.",
  };
}

export async function decideImpactAction(
  caseId: string,
  hypothesisId: string,
  expectedHypothesisSha256: string,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  if (!roles.has("reviewer") && !roles.has("domain_sme")) {
    return actionError(new CaseApiError(403, "Impact decisions require a review role."));
  }
  const intentId = formString(formData, "intent_id", 64);
  const decision = formString(formData, "decision", 16);
  const reason = formString(formData, "reason", 2_000);
  if (
    !isUuid(caseId)
    || !isUuid(hypothesisId)
    || !isUuid(intentId)
    || !SHA256_PATTERN.test(expectedHypothesisSha256)
    || (decision !== "accept" && decision !== "reject")
    || reason.length < 8
  ) {
    return { status: "error", message: "The impact decision is incomplete or stale." };
  }
  try {
    await decideAgentCaseImpact(
      caseId,
      hypothesisId,
      { decision, expectedHypothesisSha256, reason },
      `impact-decision:${hypothesisId}:${intentId}`,
    );
  } catch (error) {
    return actionError(error);
  }
  revalidatePath(`/cases/${caseId}`);
  return {
    status: "success",
    message: decision === "accept"
      ? "Hypothesis accepted as a review relationship, not a compliance conclusion."
      : "Hypothesis rejected with an attributable rationale.",
  };
}

export async function runVerificationAction(
  caseId: string,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  const intentId = formString(formData, "intent_id", 64);
  if ((!roles.has("analyst") && !roles.has("system_owner")) || !isUuid(caseId) || !isUuid(intentId)) {
    return actionError(new CaseApiError(403, "Verification is restricted."));
  }
  try {
    await verifyAgentCase(caseId, `verification:${intentId}`);
  } catch (error) {
    return actionError(error);
  }
  revalidatePath(`/cases/${caseId}`);
  return { status: "success", message: "Independent verification completed and was hash-bound to the accepted evidence." };
}

export async function composeArtifactAction(
  caseId: string,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  const intentId = formString(formData, "intent_id", 64);
  const title = formString(formData, "title", 300);
  const reviewer = formString(formData, "assigned_reviewer_id", 255);
  if ((!roles.has("analyst") && !roles.has("system_owner")) || !isUuid(caseId) || !isUuid(intentId) || !title) {
    return { status: "error", message: "The artifact composition request is incomplete." };
  }
  try {
    await composeAgentCaseArtifact(
      caseId,
      { title, assignedReviewerId: reviewer || undefined },
      `artifact-compose:${intentId}`,
    );
  } catch (error) {
    return actionError(error);
  }
  revalidatePath(`/cases/${caseId}`);
  return { status: "success", message: "An immutable draft revision was composed from PASS-verified records only." };
}

export async function decideArtifactAction(
  caseId: string,
  artifactVersionId: string,
  expectedContentSha256: string,
  expectedEvidenceManifestSha256: string,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  const intentId = formString(formData, "intent_id", 64);
  const decision = formString(formData, "decision", 24);
  const reason = formString(formData, "reason", 2_000);
  if (
    !roles.has("reviewer")
    || !isUuid(caseId)
    || !isUuid(artifactVersionId)
    || !isUuid(intentId)
    || !SHA256_PATTERN.test(expectedContentSha256)
    || !SHA256_PATTERN.test(expectedEvidenceManifestSha256)
    || !["approve", "reject", "request_revision"].includes(decision)
    || reason.length < 8
  ) {
    return { status: "error", message: "The artifact decision is incomplete or stale." };
  }
  try {
    await decideAgentCaseArtifact(
      caseId,
      artifactVersionId,
      {
        decision: decision as "approve" | "reject" | "request_revision",
        expectedContentSha256,
        expectedEvidenceManifestSha256,
        reason,
      },
      `artifact-decision:${artifactVersionId}:${intentId}`,
    );
  } catch (error) {
    return actionError(error);
  }
  revalidatePath(`/cases/${caseId}`);
  return { status: "success", message: decision === "approve" ? "Artifact revision approved and locked." : "Artifact revision returned with an attributable decision." };
}

export async function createIntegrationDraftAction(
  caseId: string,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  const intentId = formString(formData, "intent_id", 64);
  const channel = formString(formData, "channel", 32);
  const destination = formString(formData, "destination", 320);
  const title = formString(formData, "title", 300);
  const body = formString(formData, "body", 10_000);
  const runId = formString(formData, "run_id", 36);
  const channels = ["INTERNAL", "EMAIL", "SLACK", "TEAMS", "NOTION", "TASK"] as const;
  if (
    (!roles.has("analyst") && !roles.has("system_owner"))
    || !isUuid(caseId)
    || !isUuid(intentId)
    || !channels.some((item) => item === channel)
    || !destination
    || title.length < 3
    || body.length < 8
    || (runId && !isUuid(runId))
  ) {
    return { status: "error", message: "The draft handoff request is incomplete or invalid." };
  }
  try {
    await createAgentCaseIntegrationDraft(
      caseId,
      {
        channel: channel as (typeof channels)[number],
        destination,
        title,
        body,
        runId: runId || undefined,
      },
      `integration-draft:${intentId}`,
    );
  } catch (error) {
    return actionError(error);
  }
  revalidatePath(`/cases/${caseId}`);
  return {
    status: "success",
    message: "Draft recorded. PharmaAgent OS did not deliver it to the external destination.",
  };
}

export async function reviewIntegrationDraftAction(
  caseId: string,
  draftId: string,
  expectedContentSha256: string,
  intentId: string,
  _previousState: CaseActionState,
  formData: FormData,
): Promise<CaseActionState> {
  const identity = await getPortalIdentity();
  const roles = roleSet(identity.roles);
  const decision = formString(formData, "decision", 40);
  const reason = formString(formData, "reason", 2_000);
  if (
    (!roles.has("reviewer") && !roles.has("domain_sme"))
    || !isUuid(caseId)
    || !isUuid(draftId)
    || !isUuid(intentId)
    || !SHA256_PATTERN.test(expectedContentSha256)
    || !["review_for_manual_use", "cancel"].includes(decision)
    || reason.length < 8
  ) {
    return { status: "error", message: "The independent draft review is incomplete or stale." };
  }
  try {
    await reviewAgentCaseIntegrationDraft(draftId, {
      decision: decision as "review_for_manual_use" | "cancel",
      expectedContentSha256,
      reason,
    });
  } catch (error) {
    return actionError(error);
  }
  revalidatePath(`/cases/${caseId}`);
  return {
    status: "success",
    message: decision === "review_for_manual_use"
      ? "Draft reviewed for manual use; no external delivery occurred."
      : "Draft cancelled and retained in the audit record.",
  };
}
