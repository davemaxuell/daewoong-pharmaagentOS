"use client";

import { useActionState } from "react";
import {
  composeArtifactAction,
  createCaseAction,
  createIntegrationDraftAction,
  createPlanAction,
  controlRunAction,
  decideImpactAction,
  decideArtifactAction,
  decidePlanAction,
  decideRunStepAction,
  generateImpactAction,
  runVerificationAction,
  reviewIntegrationDraftAction,
  startRunAction,
} from "@/app/(portal)/cases/actions";
import {
  EMPTY_CASE_ACTION_STATE,
  type CaseRun,
  type CasePlan,
  type ArtifactVersion,
  type ImpactHypothesis,
  type IntegrationDraft,
} from "@/lib/case-types";
import styles from "./case-workbench.module.css";

function ActionMessage({ state }: { state: typeof EMPTY_CASE_ACTION_STATE }) {
  if (state.status === "idle") return <span className={styles.srStatus} aria-live="polite" />;
  return (
    <div
      className={state.status === "error" ? styles.formError : styles.formSuccess}
      role={state.status === "error" ? "alert" : "status"}
    >
      <strong>{state.status === "error" ? "Operation not completed" : "Case record updated"}</strong>
      <span>{state.message}</span>
      {state.requestId ? <small>Request ID · {state.requestId}</small> : null}
    </div>
  );
}

export function CreateCaseForm({ intentId }: { intentId: string }) {
  const [state, formAction, pending] = useActionState(
    createCaseAction,
    EMPTY_CASE_ACTION_STATE,
  );

  return (
    <form className={styles.createForm} action={formAction}>
      <input name="intent_id" type="hidden" value={intentId} />
      <div className={styles.formHeading}>
        <span>Controlled intake</span>
        <h2>Open a review case</h2>
        <p>
          Begin with one admitted FDA warning letter and its exact retained document version.
        </p>
      </div>

      <fieldset className={styles.formFields} disabled={pending}>
        <label className={styles.field} htmlFor="case-title">
          <span>Case title</span>
          <input
            id="case-title"
            name="title"
            type="text"
            maxLength={300}
            placeholder="Sterile manufacturing impact review"
            required
          />
        </label>

        <label className={styles.field} htmlFor="case-objective">
          <span>Review objective</span>
          <textarea
            id="case-objective"
            name="objective"
            rows={4}
            maxLength={4_000}
            placeholder="Determine whether the selected FDA findings may be relevant to…"
            required
          />
        </label>

        <div className={styles.fieldPair}>
          <label className={styles.field} htmlFor="warning-letter-id">
            <span>Warning-letter ID</span>
            <input
              id="warning-letter-id"
              name="warning_letter_id"
              type="text"
              minLength={36}
              maxLength={36}
              placeholder="00000000-0000-0000-0000-000000000000"
              autoComplete="off"
              spellCheck={false}
              required
            />
          </label>
          <label className={styles.field} htmlFor="document-version-id">
            <span>Document-version ID</span>
            <input
              id="document-version-id"
              name="document_version_id"
              type="text"
              minLength={36}
              maxLength={36}
              placeholder="00000000-0000-0000-0000-000000000000"
              autoComplete="off"
              spellCheck={false}
              required
            />
          </label>
        </div>

        <div className={styles.workflowLock}>
          <span>Workflow template</span>
          <strong>Regulatory impact review · v1</strong>
          <small>Read-only analysis; controlled-system writes prohibited</small>
        </div>

        <button className={styles.primaryButton} type="submit">
          {pending ? "Opening case…" : "Open governed case"}
        </button>
      </fieldset>

      <ActionMessage state={state} />
    </form>
  );
}

export function PlanComposer({ caseId, intentId }: { caseId: string; intentId: string }) {
  const action = createPlanAction.bind(null, caseId);
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);

  return (
    <details className={styles.planComposer} open>
      <summary>
        <span>Plan mode</span>
        <strong>Prepare a typed plan version</strong>
      </summary>
      <form action={formAction}>
        <input name="intent_id" type="hidden" value={intentId} />
        <fieldset className={styles.formFields} disabled={pending}>
          <label className={styles.field} htmlFor="domain-lens">
            <span>Domain lens</span>
            <input
              id="domain-lens"
              name="domain_lens"
              type="text"
              maxLength={300}
              placeholder="e.g. sterile manufacturing, data integrity, QC laboratory"
            />
            <small>Optional. Narrows analysis without changing the pinned evidence.</small>
          </label>
          <label className={styles.field} htmlFor="assigned-reviewer">
            <span>Assigned reviewer subject</span>
            <input
              id="assigned-reviewer"
              name="assigned_reviewer_id"
              type="text"
              maxLength={255}
              placeholder="Leave blank for the independent reviewer queue"
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <div className={styles.planPreview}>
            <span>4 bounded steps</span>
            <ol>
              <li>Version-bound regulatory evidence</li>
              <li>Internal evidence candidates</li>
              <li>Potential impact hypotheses</li>
              <li>Independent verification</li>
            </ol>
          </div>
          <button className={styles.primaryButton} type="submit">
            {pending ? "Creating immutable version…" : "Create plan for review"}
          </button>
        </fieldset>
        <ActionMessage state={state} />
      </form>
    </details>
  );
}

export function PlanDecisionForm({
  caseId,
  plan,
  intentId,
}: {
  caseId: string;
  plan: CasePlan;
  intentId: string;
}) {
  const action = decidePlanAction.bind(null, caseId, plan.version);
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);

  return (
    <form className={styles.decisionForm} action={formAction}>
      <input name="intent_id" type="hidden" value={intentId} />
      <input name="expected_plan_sha256" type="hidden" value={plan.planSha256} />
      <input name="expected_state_hash" type="hidden" value={plan.basedOnStateHash} />

      <div className={styles.decisionHeading}>
        <span>Independent decision</span>
        <h3>Approve this exact binding?</h3>
        <p>
          Your decision is attributable and applies only to plan v{plan.version} and the displayed case state.
        </p>
        {plan.approval.expiresAt ? (
          <small className={styles.expiryNote}>The API reconciles the displayed approval expiry when this decision is submitted.</small>
        ) : null}
      </div>
      <fieldset className={styles.formFields} disabled={pending}>
        <label className={styles.field} htmlFor={`decision-reason-${plan.id}`}>
          <span>Decision rationale</span>
          <textarea
            id={`decision-reason-${plan.id}`}
            name="reason"
            rows={3}
            minLength={8}
            maxLength={2_000}
            placeholder="Record the evidence and reasoning for this decision."
            required
          />
        </label>
        <div className={styles.decisionActions}>
          <button className={styles.rejectButton} type="submit" name="decision" value="reject">
            {pending ? "Recording…" : "Reject plan"}
          </button>
          <button className={styles.approveButton} type="submit" name="decision" value="approve">
            {pending ? "Recording…" : "Approve bound plan"}
          </button>
        </div>
      </fieldset>
      <ActionMessage state={state} />
    </form>
  );
}

export function RunStartForm({
  caseId,
  plan,
  intentId,
}: {
  caseId: string;
  plan: CasePlan;
  intentId: string;
}) {
  const action = startRunAction.bind(
    null,
    caseId,
    plan.version,
    plan.planSha256,
    plan.basedOnStateHash,
  );
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);
  return (
    <form className={styles.runStartForm} action={formAction}>
      <input name="intent_id" type="hidden" value={intentId} />
      <div>
        <span>Exact approved binding</span>
        <strong>Start plan v{plan.version}</strong>
        <small>The run will use the displayed plan, state, workflow, agents, tools, and limits.</small>
      </div>
      <button className={styles.primaryButton} type="submit" disabled={pending}>
        {pending ? "Starting durable run…" : "Start approved run"}
      </button>
      <ActionMessage state={state} />
    </form>
  );
}

export function RunControlForm({
  caseId,
  run,
  intentId,
}: {
  caseId: string;
  run: CaseRun;
  intentId: string;
}) {
  const operation = run.status === "PAUSED" ? "resume" : "pause";
  const action = controlRunAction.bind(null, caseId, run.id, operation);
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);
  const cancelAction = controlRunAction.bind(null, caseId, run.id, "cancel");
  const [cancelState, cancelFormAction, cancelling] = useActionState(
    cancelAction,
    EMPTY_CASE_ACTION_STATE,
  );
  return (
    <div className={styles.runControlForms}>
      <form action={formAction}>
        <input name="intent_id" type="hidden" value={intentId} />
        <label className={styles.field} htmlFor={`run-reason-${run.id}`}>
          <span>Control rationale</span>
          <textarea
            id={`run-reason-${run.id}`}
            name="reason"
            rows={2}
            minLength={8}
            maxLength={2_000}
            placeholder="Record why this run should change state."
            required
          />
        </label>
        <button className={styles.primaryButton} type="submit" disabled={pending}>
          {pending ? "Recording…" : operation === "pause" ? "Pause run" : "Resume run"}
        </button>
        <ActionMessage state={state} />
      </form>
      <form action={cancelFormAction}>
        <input name="intent_id" type="hidden" value={intentId} />
        <input name="reason" type="hidden" value="User cancelled this governed case run." />
        <button className={styles.rejectButton} type="submit" disabled={cancelling}>
          {cancelling ? "Cancelling…" : "Cancel run"}
        </button>
        <ActionMessage state={cancelState} />
      </form>
    </div>
  );
}

export function RunStepDecisionForm({
  caseId,
  run,
  intentId,
}: {
  caseId: string;
  run: CaseRun;
  intentId: string;
}) {
  const stepKey = run.checkpoint.stepKey;
  const step = stepKey ? run.checkpoint.steps[stepKey] : undefined;
  const action = decideRunStepAction.bind(
    null,
    caseId,
    run.id,
    stepKey ?? "unavailable",
    step?.approvalId ?? "unavailable",
  );
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);
  if (!stepKey || !step?.approvalId) return null;
  return (
    <form className={styles.decisionForm} action={formAction}>
      <input name="intent_id" type="hidden" value={intentId} />
      <div className={styles.decisionHeading}>
        <span>Step-level interrupt</span>
        <h3>Authorize {stepKey.replaceAll("_", " ")}?</h3>
        <p>This decision applies only to invocation attempt {step.attempt} in run {run.id.slice(0, 8)}.</p>
      </div>
      <fieldset className={styles.formFields} disabled={pending}>
        <label className={styles.field} htmlFor={`step-reason-${run.id}`}>
          <span>Decision rationale</span>
          <textarea
            id={`step-reason-${run.id}`}
            name="reason"
            rows={3}
            minLength={8}
            maxLength={2_000}
            required
          />
        </label>
        <div className={styles.decisionActions}>
          <button className={styles.rejectButton} name="decision" value="reject" type="submit">
            Reject step
          </button>
          <button className={styles.approveButton} name="decision" value="approve" type="submit">
            Approve step
          </button>
        </div>
      </fieldset>
      <ActionMessage state={state} />
    </form>
  );
}

export function ImpactGenerateForm({
  caseId,
  intentId,
}: {
  caseId: string;
  intentId: string;
}) {
  const action = generateImpactAction.bind(null, caseId);
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);
  return (
    <form className={styles.impactGenerateForm} action={formAction}>
      <input name="intent_id" type="hidden" value={intentId} />
      <div>
        <span>Authorized retrieval</span>
        <strong>Generate impact hypotheses</strong>
        <small>Only approved external findings and assets visible to your identity are compared.</small>
      </div>
      <label className={styles.field} htmlFor={`impact-query-${caseId}`}>
        <span>Optional focus</span>
        <input
          id={`impact-query-${caseId}`}
          name="query"
          type="text"
          maxLength={500}
          placeholder="Data integrity, aseptic processing, validation…"
        />
      </label>
      <button className={styles.primaryButton} type="submit" disabled={pending}>
        {pending ? "Comparing evidence…" : "Generate review candidates"}
      </button>
      <ActionMessage state={state} />
    </form>
  );
}

export function ImpactDecisionForm({
  caseId,
  hypothesis,
  intentId,
}: {
  caseId: string;
  hypothesis: ImpactHypothesis;
  intentId: string;
}) {
  const action = decideImpactAction.bind(
    null,
    caseId,
    hypothesis.id,
    hypothesis.hypothesisSha256,
  );
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);
  return (
    <form className={styles.impactDecisionForm} action={formAction}>
      <input name="intent_id" type="hidden" value={intentId} />
      <label className={styles.field} htmlFor={`impact-reason-${hypothesis.id}`}>
        <span>Review rationale</span>
        <textarea
          id={`impact-reason-${hypothesis.id}`}
          name="reason"
          rows={2}
          minLength={8}
          maxLength={2_000}
          placeholder="Explain whether the two evidence paths support this relationship."
          required
        />
      </label>
      <div className={styles.decisionActions}>
        <button className={styles.rejectButton} name="decision" value="reject" type="submit" disabled={pending}>
          Reject
        </button>
        <button className={styles.approveButton} name="decision" value="accept" type="submit" disabled={pending}>
          Accept hypothesis
        </button>
      </div>
      <ActionMessage state={state} />
    </form>
  );
}

export function VerificationControlForm({ caseId, intentId }: { caseId: string; intentId: string }) {
  const action = runVerificationAction.bind(null, caseId);
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);
  return (
    <form className={styles.impactGenerateForm} action={formAction}>
      <input name="intent_id" type="hidden" value={intentId} />
      <div>
        <span>Independent challenge</span>
        <strong>Run verification</strong>
        <small>Resolve exact anchors, test semantic support, and enforce the two-correction ceiling.</small>
      </div>
      <button className={styles.primaryButton} type="submit" disabled={pending}>
        {pending ? "Verifying…" : "Verify accepted records"}
      </button>
      <ActionMessage state={state} />
    </form>
  );
}

export function ArtifactComposeForm({ caseId, intentId }: { caseId: string; intentId: string }) {
  const action = composeArtifactAction.bind(null, caseId);
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);
  return (
    <form className={styles.impactDecisionForm} action={formAction}>
      <input name="intent_id" type="hidden" value={intentId} />
      <label className={styles.field} htmlFor={`artifact-title-${caseId}`}>
        <span>Immutable report title</span>
        <input id={`artifact-title-${caseId}`} name="title" maxLength={300} defaultValue="Regulatory Impact Review Package" required />
      </label>
      <label className={styles.field} htmlFor={`artifact-reviewer-${caseId}`}>
        <span>Assigned reviewer subject (optional)</span>
        <input id={`artifact-reviewer-${caseId}`} name="assigned_reviewer_id" maxLength={255} placeholder="qa.reviewer@example.test" />
      </label>
      <button className={styles.primaryButton} type="submit" disabled={pending}>
        {pending ? "Composing…" : "Compose from verified records"}
      </button>
      <ActionMessage state={state} />
    </form>
  );
}

export function ArtifactDecisionForm({
  caseId,
  artifact,
  intentId,
}: {
  caseId: string;
  artifact: ArtifactVersion;
  intentId: string;
}) {
  const action = decideArtifactAction.bind(
    null,
    caseId,
    artifact.id,
    artifact.contentSha256,
    artifact.evidenceManifestSha256,
  );
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);
  return (
    <form className={styles.impactDecisionForm} action={formAction}>
      <input name="intent_id" type="hidden" value={intentId} />
      <label className={styles.field} htmlFor={`artifact-reason-${artifact.id}`}>
        <span>Independent QA rationale</span>
        <textarea id={`artifact-reason-${artifact.id}`} name="reason" rows={3} minLength={8} maxLength={2_000} required />
      </label>
      <div className={styles.decisionActions}>
        <button className={styles.rejectButton} name="decision" value="reject" type="submit" disabled={pending}>Reject</button>
        <button className={styles.rejectButton} name="decision" value="request_revision" type="submit" disabled={pending}>Request revision</button>
        <button className={styles.approveButton} name="decision" value="approve" type="submit" disabled={pending}>Approve and lock</button>
      </div>
      <ActionMessage state={state} />
    </form>
  );
}

export function IntegrationDraftForm({
  caseId,
  intentId,
  runId,
}: {
  caseId: string;
  intentId: string;
  runId?: string;
}) {
  const action = createIntegrationDraftAction.bind(null, caseId);
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);
  return (
    <form className={styles.integrationForm} action={formAction}>
      <input name="intent_id" type="hidden" value={intentId} />
      {runId ? <input name="run_id" type="hidden" value={runId} /> : null}
      <div className={styles.formHeading}>
        <span>Draft-only handoff</span>
        <strong>Prepare content for a human-operated channel</strong>
        <p>The platform records a bounded draft and never sends, posts, assigns, or publishes it.</p>
      </div>
      <div className={styles.integrationFields}>
        <label className={styles.field}>
          <span>Channel</span>
          <select name="channel" defaultValue="INTERNAL">
            <option value="INTERNAL">Internal</option>
            <option value="EMAIL">Email</option>
            <option value="SLACK">Slack</option>
            <option value="TEAMS">Teams</option>
            <option value="NOTION">Notion</option>
            <option value="TASK">Task</option>
          </select>
        </label>
        <label className={styles.field}>
          <span>Intended destination</span>
          <input name="destination" maxLength={320} placeholder="Named queue, person, or channel" required />
        </label>
      </div>
      <label className={styles.field}>
        <span>Draft title</span>
        <input name="title" minLength={3} maxLength={300} required />
      </label>
      <label className={styles.field}>
        <span>Draft body · decision support only</span>
        <textarea name="body" rows={7} minLength={8} maxLength={10_000} required />
      </label>
      <button className={styles.primaryButton} type="submit" disabled={pending}>
        {pending ? "Recording…" : "Record draft without delivery"}
      </button>
      <ActionMessage state={state} />
    </form>
  );
}

export function IntegrationDraftReviewForm({
  caseId,
  draft,
  intentId,
}: {
  caseId: string;
  draft: IntegrationDraft;
  intentId: string;
}) {
  const action = reviewIntegrationDraftAction.bind(
    null,
    caseId,
    draft.id,
    draft.contentSha256,
    intentId,
  );
  const [state, formAction, pending] = useActionState(action, EMPTY_CASE_ACTION_STATE);
  return (
    <form className={styles.impactDecisionForm} action={formAction}>
      <label className={styles.field}>
        <span>Independent review rationale</span>
        <textarea name="reason" rows={3} minLength={8} maxLength={2_000} required />
      </label>
      <div className={styles.decisionActions}>
        <button className={styles.rejectButton} name="decision" value="cancel" type="submit" disabled={pending}>Cancel draft</button>
        <button className={styles.approveButton} name="decision" value="review_for_manual_use" type="submit" disabled={pending}>Review for manual use</button>
      </div>
      <ActionMessage state={state} />
    </form>
  );
}
