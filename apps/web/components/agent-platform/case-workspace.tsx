import Link from "next/link";
import {
  ArrowLeft,
  ArrowUpRight,
  Activity,
  CheckCircle2,
  CircleAlert,
  FileText,
  History,
  GitBranch,
  LockKeyhole,
  Send,
  ShieldCheck,
} from "lucide-react";
import {
  ArtifactComposeForm,
  ArtifactDecisionForm,
  PlanComposer,
  ImpactDecisionForm,
  ImpactGenerateForm,
  IntegrationDraftForm,
  IntegrationDraftReviewForm,
  PlanDecisionForm,
  RunControlForm,
  RunStartForm,
  RunStepDecisionForm,
  VerificationControlForm,
} from "@/components/agent-platform/case-forms";
import { RunLiveRefresh } from "@/components/agent-platform/run-live-refresh";
import {
  caseStatusTone,
  formatCaseStatus,
  isPlanBindingCurrent,
  shortHash,
  type AgentCase,
  type ArtifactVersion,
  type CaseEvent,
  type CasePlan,
  type CaseRun,
  type CaseWorkspaceView,
  type ImpactMap,
  type IntegrationDraft,
  type RunEvent,
  type VerificationReport,
} from "@/lib/case-types";
import styles from "./case-workbench.module.css";

const WORKSPACE_VIEWS: Array<{ id: CaseWorkspaceView; label: string; note: string }> = [
  { id: "overview", label: "Overview", note: "Scope" },
  { id: "plan", label: "Plan", note: "Approval" },
  { id: "execution", label: "Execution", note: "Live run" },
  { id: "impact", label: "Impact", note: "Hypotheses" },
  { id: "review", label: "QA Review", note: "Verification" },
  { id: "integrations", label: "Handoffs", note: "Draft only" },
  { id: "evidence", label: "Evidence", note: "Versions" },
  { id: "history", label: "History", note: "Audit" },
];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function payloadText(event: CaseEvent): string {
  const payload = event.payload;
  if (event.eventType === "CASE_CREATED") {
    return typeof payload.workflow_key === "string"
      ? `Workflow ${payload.workflow_key} established.`
      : "Case identity and objective established.";
  }
  if (event.eventType === "SOURCE_PINNED") {
    const versionId = typeof payload.document_version_id === "string" ? payload.document_version_id : "exact version";
    return `Immutable source ${shortHash(versionId, 6)} pinned.`;
  }
  if (event.eventType === "PLAN_GENERATED") {
    const version = typeof payload.plan_version === "number" ? `v${payload.plan_version}` : "version";
    return `Plan ${version} generated against the current case state.`;
  }
  if (event.eventType === "APPROVAL_REQUESTED") return "Independent plan approval requested.";
  if (event.eventType === "PLAN_APPROVED") return "Bound plan approved by an independent reviewer.";
  if (event.eventType === "PLAN_REJECTED") {
    return typeof payload.reason === "string" ? payload.reason : "Plan rejected for revision.";
  }
  return "Recorded in the immutable case event stream.";
}

function HashField({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.hashField}>
      <span>{label}</span>
      <code title={value}>{value}</code>
      <small>{shortHash(value, 10)}</small>
    </div>
  );
}

function OverviewPanel({ agentCase, plan }: { agentCase: AgentCase; plan?: CasePlan }) {
  return (
    <div className={styles.workspacePanel}>
      <section className={styles.objectiveSheet}>
        <p className={styles.sectionIndex}>01 / objective</p>
        <h2>Question under review</h2>
        <p className={styles.objectiveCopy}>{agentCase.objective}</p>
        <dl className={styles.definitionGrid}>
          <div><dt>Workflow</dt><dd>{agentCase.workflowKey}</dd></div>
          <div><dt>Owner subject</dt><dd>{agentCase.ownerSubject}</dd></div>
          <div><dt>Opened</dt><dd>{formatDate(agentCase.createdAt)}</dd></div>
          <div><dt>Latest activity</dt><dd>{formatDate(agentCase.updatedAt)}</dd></div>
        </dl>
      </section>

      <section className={styles.scopeSheet}>
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.sectionIndex}>02 / controlled scope</p>
            <h2>Version-bound inputs</h2>
          </div>
          <LockKeyhole size={20} aria-hidden="true" />
        </div>
        <p>
          Source pins are immutable. A newer FDA retrieval does not silently replace the evidence used by this case.
        </p>
        <ol className={styles.sourceSummaryList}>
          {agentCase.sources.map((source) => (
            <li key={source.id}>
              <span>A</span>
              <div>
                <strong>Official FDA warning letter · version {source.documentVersionNumber}</strong>
                <small>{source.sourceRole.replaceAll("_", " ")} · pinned {formatDate(source.createdAt)}</small>
              </div>
              <code title={source.sourceSha256}>{shortHash(source.sourceSha256, 7)}</code>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.readinessSheet}>
        <p className={styles.sectionIndex}>03 / readiness</p>
        <div className={styles.readinessLine}>
          {plan?.approval.status === "APPROVED" ? (
            <CheckCircle2 size={21} aria-hidden="true" />
          ) : (
            <CircleAlert size={21} aria-hidden="true" />
          )}
          <div>
            <strong>{plan ? `Plan v${plan.version} · ${formatCaseStatus(plan.approval.status)}` : "No plan version yet"}</strong>
            <p>{plan
              ? "The approved plan can start only against its exact workflow and state binding."
              : "Create a typed plan before any specialist workflow can be considered ready."}</p>
          </div>
          <Link href={`/cases/${agentCase.id}?view=plan`}>Inspect plan</Link>
        </div>
      </section>
    </div>
  );
}

function runEventText(event: RunEvent): string {
  const step = typeof event.payload.step_key === "string"
    ? event.payload.step_key.replaceAll("_", " ")
    : undefined;
  if (event.eventType === "RUN_STARTED") return "Run accepted and queued for durable execution.";
  if (event.eventType === "AGENT_STARTED") return `${step ?? "Specialist"} started.`;
  if (event.eventType === "AGENT_COMPLETED") return `${step ?? "Specialist"} completed.`;
  if (event.eventType === "APPROVAL_REQUESTED") return `${step ?? "Step"} awaits independent approval.`;
  if (event.eventType === "APPROVAL_DECIDED") {
    return `${step ?? "Step"} ${event.payload.decision === "approve" ? "approved" : "rejected"}.`;
  }
  if (event.eventType === "LIMIT_EXCEEDED") return "Runtime stopped work at a hard limit.";
  return event.eventType.replaceAll("_", " ").toLocaleLowerCase();
}

function ExecutionPanel({
  agentCase,
  plan,
  run,
  runEvents,
  runLoadError,
  runIntentId,
  stepDecisionIntentId,
  canControlRun,
  canDecideStep,
}: {
  agentCase: AgentCase;
  plan?: CasePlan;
  run?: CaseRun;
  runEvents: RunEvent[];
  runLoadError?: string;
  runIntentId: string;
  stepDecisionIntentId: string;
  canControlRun: boolean;
  canDecideStep: boolean;
}) {
  if (runLoadError) {
    return (
      <section className={styles.panelError} role="alert">
        <CircleAlert size={22} aria-hidden="true" />
        <div><strong>Run state could not be loaded.</strong><p>{runLoadError}</p></div>
      </section>
    );
  }
  if (!run) {
    const ready = agentCase.status === "READY"
      && plan?.approval.status === "APPROVED"
      && isPlanBindingCurrent(plan, agentCase);
    return (
      <div className={styles.workspacePanel}>
        <section className={styles.noPlan}>
          <p className={styles.sectionIndex}>Execution / not started</p>
          <h2>Start only from an exact approved binding.</h2>
          <p>The durable runtime revalidates the plan, source state, workflow release, agent versions, tool permissions, and budgets before dispatch.</p>
        </section>
        {ready && canControlRun && plan ? (
          <RunStartForm caseId={agentCase.id} plan={plan} intentId={runIntentId} />
        ) : (
          <section className={styles.readOnlyNotice}>
            <LockKeyhole size={18} aria-hidden="true" />
            <div>
              <strong>{ready ? "Awaiting the case owner." : "Run start is locked."}</strong>
              <p>{ready
                ? "A Regulatory Analyst or System Owner can start this approved plan."
                : "Create and independently approve a current plan before execution."}</p>
            </div>
          </section>
        )}
      </div>
    );
  }
  const terminal = ["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"].includes(run.status);
  return (
    <div className={styles.workspacePanel}>
      <RunLiveRefresh status={run.status} />
      <section className={styles.runHeader}>
        <div>
          <p className={styles.sectionIndex}>Run / {run.id.slice(0, 8).toLocaleUpperCase()}</p>
          <h2>{formatCaseStatus(run.status)}</h2>
          <p>
            Workflow {run.checkpoint.workflowTemplate.workflowKey} · v{run.checkpoint.workflowTemplate.version}
            {run.checkpoint.stepKey ? ` · ${run.checkpoint.stepKey.replaceAll("_", " ")}` : ""}
          </p>
        </div>
        <div className={styles.runCheckpoint}>
          <span>Checkpoint</span>
          <strong>v{run.checkpoint.checkpointVersion}</strong>
          <small>{run.activeInvocation ? `Attempt ${run.activeInvocation.attempt}` : "No active invocation"}</small>
        </div>
      </section>

      {canControlRun && !terminal ? (
        <RunControlForm caseId={agentCase.id} run={run} intentId={runIntentId} />
      ) : null}
      {canDecideStep && run.status === "WAITING_FOR_APPROVAL" ? (
        <RunStepDecisionForm
          caseId={agentCase.id}
          run={run}
          intentId={stepDecisionIntentId}
        />
      ) : null}

      <section className={styles.runSteps}>
        <div className={styles.sectionHeading}>
          <div><p className={styles.sectionIndex}>Persisted graph</p><h2>Plan-step state</h2></div>
          <Activity size={21} aria-hidden="true" />
        </div>
        <ol>
          {plan?.steps.map((step) => {
            const state = run.checkpoint.steps[step.stepKey];
            return (
              <li key={step.id} data-status={state?.status.toLocaleLowerCase()}>
                <span>{String(step.position).padStart(2, "0")}</span>
                <div><strong>{step.title}</strong><small>{state ? formatCaseStatus(state.status) : "Unavailable"}</small></div>
                <code>{state?.outputSha256 ? shortHash(state.outputSha256, 6) : state?.attempt ? `attempt ${state.attempt}` : "pending"}</code>
              </li>
            );
          })}
        </ol>
      </section>

      <section className={styles.runBudget}>
        <div><span>Turns</span><strong>{run.checkpoint.budget.turns}</strong></div>
        <div><span>Tool calls</span><strong>{run.checkpoint.budget.toolCalls}</strong></div>
        <div><span>Tokens</span><strong>{run.checkpoint.budget.inputTokens + run.checkpoint.budget.outputTokens}</strong></div>
        <div><span>Runtime</span><strong>{run.checkpoint.budget.runtimeSeconds.toFixed(1)}s</strong></div>
        <div><span>Cost</span><strong>${run.checkpoint.budget.costUsd.toFixed(2)}</strong></div>
      </section>

      <section className={styles.runTimeline}>
        <div className={styles.sectionHeading}>
          <div><p className={styles.sectionIndex}>Live timeline</p><h2>{runEvents.length} run events</h2></div>
          <small>{terminal ? "Final" : "Refreshes every 2 seconds"}</small>
        </div>
        <ol>
          {runEvents.map((event) => (
            <li key={event.id}>
              <span>{String(event.sequence).padStart(3, "0")}</span>
              <div><strong>{runEventText(event)}</strong><small>{event.actorId} · {formatDate(event.occurredAt)}</small></div>
              <code title={event.eventHash}>{shortHash(event.eventHash, 6)}</code>
            </li>
          ))}
        </ol>
      </section>
      {run.errorCode ? (
        <section className={styles.panelError} role="alert">
          <CircleAlert size={22} aria-hidden="true" />
          <div><strong>Run stopped.</strong><p>{run.errorCode.replaceAll("_", " ")}</p></div>
        </section>
      ) : null}
    </div>
  );
}

function ImpactPanel({
  agentCase,
  impact,
  impactLoadError,
  impactIntentId,
  canGenerateImpact,
  canReviewImpact,
}: {
  agentCase: AgentCase;
  impact?: ImpactMap;
  impactLoadError?: string;
  impactIntentId: string;
  canGenerateImpact: boolean;
  canReviewImpact: boolean;
}) {
  if (impactLoadError) {
    return (
      <section className={styles.panelError} role="alert">
        <CircleAlert size={22} aria-hidden="true" />
        <div><strong>Impact map could not be loaded.</strong><p>{impactLoadError}</p></div>
      </section>
    );
  }
  const items = impact?.items ?? [];
  return (
    <div className={styles.workspacePanel}>
      <section className={styles.impactHeader}>
        <div>
          <p className={styles.sectionIndex}>Evidence relationship studio</p>
          <h2>{items.length} reviewable impact hypotheses</h2>
          <p>{impact?.notice ?? "Generate bounded comparisons from approved external findings and authorized synthetic internal evidence."}</p>
        </div>
        <GitBranch size={23} aria-hidden="true" />
      </section>

      {canGenerateImpact ? (
        <ImpactGenerateForm caseId={agentCase.id} intentId={impactIntentId} />
      ) : null}

      {items.length ? (
        <ol className={styles.impactMap}>
          {items.map((item) => (
            <li key={item.id} data-status={item.status.toLocaleLowerCase()}>
              <div className={styles.impactCardHeader}>
                <div>
                  <span>{item.reviewPriority} priority · {item.status}</span>
                  <h3>{item.assetKey} · rev {item.revision}</h3>
                  <small>{item.assetType} / {item.assetDomain} / {item.effectiveStatus}</small>
                </div>
                <strong>{Math.round(item.confidence * 100)}%</strong>
              </div>
              <p className={styles.impactStatement}>{item.statement}</p>
              <div className={styles.evidenceBridge}>
                <article>
                  <span>External regulatory evidence</span>
                  <strong>{item.externalEvidence[0]?.anchorId ?? "Missing anchor"}</strong>
                  <p>{item.externalEvidence[0]?.excerpt}</p>
                </article>
                <GitBranch size={18} aria-label="proposed relationship" />
                <article>
                  <span>Internal synthetic evidence</span>
                  <strong>{item.internalEvidence[0]?.anchorId ?? "Missing anchor"}</strong>
                  <p>{item.internalEvidence[0]?.excerpt}</p>
                </article>
              </div>
              <div className={styles.impactReasoning}>
                <div><span>Assumption</span><p>{item.assumptions[0]}</p></div>
                <div><span>Counterevidence</span><p>{item.counterevidence[0]}</p></div>
                <div><span>Unknown</span><p>{item.unknowns[0]}</p></div>
                <div><span>Human verification</span><p>{item.recommendedVerification[0]}</p></div>
              </div>
              <HashField label="Hypothesis SHA-256" value={item.hypothesisSha256} />
              {canReviewImpact && item.status === "PROPOSED" ? (
                <ImpactDecisionForm
                  caseId={agentCase.id}
                  hypothesis={item}
                  intentId={impactIntentId}
                />
              ) : null}
              {item.reviewedBy ? (
                <p className={styles.immutabilityNote}>
                  <LockKeyhole size={14} aria-hidden="true" />
                  Reviewed by {item.reviewedBy} · {item.reviewReason}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <section className={styles.noPlan}>
          <h2>No internal relationships have been proposed.</h2>
          <p>Only reviewed findings are eligible. Retrieval applies your asset ACL before ranking and never reveals inaccessible titles or content.</p>
        </section>
      )}
    </div>
  );
}

function ReviewPanel({
  agentCase,
  verification,
  artifacts,
  loadError,
  verificationIntentId,
  artifactIntentId,
  canRunVerification,
  canComposeArtifact,
  canReviewArtifact,
}: {
  agentCase: AgentCase;
  verification?: VerificationReport | null;
  artifacts: ArtifactVersion[];
  loadError?: string;
  verificationIntentId: string;
  artifactIntentId: string;
  canRunVerification: boolean;
  canComposeArtifact: boolean;
  canReviewArtifact: boolean;
}) {
  if (loadError) {
    return <section className={styles.panelError} role="alert"><CircleAlert size={22} /><div><strong>QA review records could not be loaded.</strong><p>{loadError}</p></div></section>;
  }
  return (
    <div className={styles.workspacePanel}>
      <section className={styles.impactHeader}>
        <div><p className={styles.sectionIndex}>Independent verification</p><h2>{verification ? `${verification.status} · correction ${verification.correctionIteration}/2` : "Not yet verified"}</h2><p>Artifacts can be composed only from an exact PASS report and remain draft until an independent QA reviewer decides the bound hashes.</p></div>
        <ShieldCheck size={24} aria-hidden="true" />
      </section>
      {canRunVerification ? <VerificationControlForm caseId={agentCase.id} intentId={verificationIntentId} /> : null}
      {verification ? (
        <section className={styles.bindingPanel} data-current={verification.status === "PASS"}>
          <div><ShieldCheck size={20} /><span><strong>{verification.verifier}</strong><small>{verification.checks.filter((item) => item.status === "PASS").length}/{verification.checks.length} checks passed · independent context</small></span></div>
          <HashField label="Verification report SHA-256" value={verification.reportSha256} />
          <HashField label="Verified input SHA-256" value={verification.inputSha256} />
        </section>
      ) : null}
      {verification?.issues.length ? (
        <ol className={styles.impactMap}>
          {verification.issues.map((issue, index) => (
            <li key={`${issue.code}:${index}`} data-status="rejected">
              <div className={styles.impactCardHeader}><div><span>{issue.severity}</span><h3>{issue.code.replaceAll("_", " ")}</h3></div></div>
              <p className={styles.impactStatement}>{issue.reason}</p>
              <div className={styles.impactReasoning}><div><span>Affected claim</span><p>{issue.affectedClaim}</p></div><div><span>Required correction</span><p>{issue.requiredCorrection}</p></div></div>
            </li>
          ))}
        </ol>
      ) : null}
      {canComposeArtifact && verification?.status === "PASS" ? <ArtifactComposeForm caseId={agentCase.id} intentId={artifactIntentId} /> : null}
      {artifacts.length ? (
        <ol className={styles.impactMap}>
          {artifacts.map((artifact) => (
            <li key={artifact.id} data-status={artifact.status.toLocaleLowerCase()}>
              <div className={styles.impactCardHeader}><div><span>Revision {artifact.version} · {artifact.status}</span><h3>{artifact.title}</h3><small>{artifact.evidence.length} exact external evidence members</small></div></div>
              <HashField label="Artifact content SHA-256" value={artifact.contentSha256} />
              <HashField label="Evidence manifest SHA-256" value={artifact.evidenceManifestSha256} />
              <p className={styles.immutabilityNote}><LockKeyhole size={14} /> Verification {shortHash(artifact.verificationReportId, 7)} · approval {artifact.approval.status}</p>
              {canReviewArtifact && artifact.status === "DRAFT" ? <ArtifactDecisionForm caseId={agentCase.id} artifact={artifact} intentId={artifactIntentId} /> : null}
              {artifact.status === "APPROVED" ? <a href={`/api/cases/${agentCase.id}/artifacts/${artifact.id}/export`}>Export approved JSON <ArrowUpRight size={14} /></a> : null}
              {artifact.approval.decisionReason ? <blockquote>{artifact.approval.decisionReason}</blockquote> : null}
            </li>
          ))}
        </ol>
      ) : <section className={styles.noPlan}><h2>No artifact revisions yet.</h2><p>A PASS verification is required before deterministic composition.</p></section>}
    </div>
  );
}

function PlanPanel({
  agentCase,
  plan,
  planLoadError,
  planIntentId,
  decisionIntentId,
  canAuthorPlan,
  canDecidePlan,
}: {
  agentCase: AgentCase;
  plan?: CasePlan;
  planLoadError?: string;
  planIntentId: string;
  decisionIntentId: string;
  canAuthorPlan: boolean;
  canDecidePlan: boolean;
}) {
  if (planLoadError) {
    return (
      <section className={styles.panelError} role="alert">
        <CircleAlert size={22} aria-hidden="true" />
        <div><strong>Plan version could not be loaded.</strong><p>{planLoadError}</p></div>
      </section>
    );
  }

  if (!plan) {
    return (
      <div className={styles.workspacePanel}>
        <section className={styles.noPlan}>
          <p className={styles.sectionIndex}>Plan mode / not started</p>
          <h2>Make the route inspectable before work begins.</h2>
          <p>The first plan version declares dependencies, output contracts, risk classes, and hard execution limits.</p>
        </section>
        {canAuthorPlan ? (
          <PlanComposer caseId={agentCase.id} intentId={planIntentId} />
        ) : (
          <section className={styles.readOnlyNotice}>
            <LockKeyhole size={18} aria-hidden="true" />
            <div><strong>Awaiting plan authoring.</strong><p>A Regulatory Analyst or System Owner must create the first typed plan.</p></div>
          </section>
        )}
      </div>
    );
  }

  const bindingCurrent = isPlanBindingCurrent(plan, agentCase);
  const canRevise = ["REJECTED", "CANCELLED", "EXPIRED"].includes(plan.approval.status)
    || agentCase.status === "NEEDS_REVISION";

  return (
    <div className={styles.workspacePanel}>
      <section className={styles.planHeader}>
        <div>
          <p className={styles.sectionIndex}>Plan version {String(plan.version).padStart(2, "0")}</p>
          <h2>{plan.objective}</h2>
        </div>
        <div className={styles.approvalStamp} data-status={plan.approval.status.toLocaleLowerCase()}>
          <span>Plan approval</span>
          <strong>{formatCaseStatus(plan.approval.status)}</strong>
          <small>Schema {plan.planSchemaVersion}</small>
          {plan.approval.expiresAt && plan.approval.status === "PENDING" ? (
            <small>Expires {formatDate(plan.approval.expiresAt)}</small>
          ) : null}
        </div>
      </section>

      <section className={styles.bindingPanel} data-current={bindingCurrent}>
        <div>
          <ShieldCheck size={20} aria-hidden="true" />
          <span>
            <strong>{bindingCurrent ? "Approval binding is current" : "Approval binding is stale"}</strong>
            <small>Plan, approval request, and current case state must agree exactly.</small>
          </span>
        </div>
        <HashField label="Plan SHA-256" value={plan.planSha256} />
        <HashField label="Bound state SHA-256" value={plan.basedOnStateHash} />
      </section>

      <section className={styles.planSequence} aria-labelledby="plan-sequence-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.sectionIndex}>Execution sequence</p>
            <h2 id="plan-sequence-title">{plan.steps.length} typed steps</h2>
          </div>
          <span className={styles.schemaNote}>Outputs are schema-bound</span>
        </div>
        <ol>
          {plan.steps.map((step) => (
            <li key={step.id}>
              <span className={styles.stepNumber}>{String(step.position).padStart(2, "0")}</span>
              <div className={styles.stepBody}>
                <div className={styles.stepHeading}>
                  <div><span>{step.stepKey}</span><h3>{step.title}</h3></div>
                  <span className={styles.riskMarker} data-risk={step.riskLevel}>{step.riskLevel}</span>
                </div>
                <p>{step.instructions}</p>
                <dl className={styles.stepMeta}>
                  <div><dt>Depends on</dt><dd>{step.dependsOn.length ? step.dependsOn.join(", ") : "Case inputs"}</dd></div>
                  <div><dt>Output contract</dt><dd>{step.outputSchemaRef}</dd></div>
                  <div><dt>Hard limit</dt><dd>{step.limits.maxToolCalls} tool calls · {step.limits.maxRuntimeSeconds}s · ${step.limits.maxCostUsd.toFixed(2)}</dd></div>
                  <div><dt>Step approval</dt><dd>{step.requiresApproval ? "Required" : "Covered by approved plan"}</dd></div>
                </dl>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <details className={styles.prohibitedActions}>
        <summary>Hard-prohibited actions · {plan.prohibitedActions.length}</summary>
        <ul>{plan.prohibitedActions.map((action) => <li key={action}>{action.replaceAll("_", " ")}</li>)}</ul>
      </details>

      {plan.approval.status === "PENDING" ? (
        bindingCurrent && canDecidePlan ? (
          <PlanDecisionForm
            key={`${plan.id}:${plan.approval.status}`}
            caseId={agentCase.id}
            plan={plan}
            intentId={decisionIntentId}
          />
        ) : bindingCurrent ? (
          <section className={styles.readOnlyNotice}>
            <LockKeyhole size={18} aria-hidden="true" />
            <div>
              <strong>Awaiting assigned QA review.</strong>
              <p>Only an independent QA Reviewer can decide this exact plan and state binding.</p>
            </div>
          </section>
        ) : (
          <section className={styles.panelError} role="alert">
            <CircleAlert size={22} aria-hidden="true" />
            <div><strong>Decision blocked.</strong><p>The plan no longer matches the current case state. Create a new plan version.</p></div>
          </section>
        )
      ) : (
        <section className={styles.decisionRecord}>
          <span>Decision record</span>
          <div>
            <strong>{formatCaseStatus(plan.approval.status)}</strong>
            <small>{plan.approval.decisionBy ?? "No decision identity recorded"} · {plan.approval.decidedAt ? formatDate(plan.approval.decidedAt) : "Not decided"}</small>
          </div>
          {plan.approval.decisionReason ? <blockquote>{plan.approval.decisionReason}</blockquote> : null}
        </section>
      )}

      {canRevise && canAuthorPlan ? <PlanComposer caseId={agentCase.id} intentId={planIntentId} /> : null}
      {canRevise && !canAuthorPlan ? (
        <section className={styles.readOnlyNotice}>
          <LockKeyhole size={18} aria-hidden="true" />
          <div><strong>Revision is awaiting the case owner.</strong><p>A Regulatory Analyst or System Owner must issue a new immutable plan version.</p></div>
        </section>
      ) : null}
    </div>
  );
}

function IntegrationsPanel({
  agentCase,
  run,
  drafts,
  loadError,
  createIntentId,
  reviewIntentId,
  canCreate,
  canReview,
}: {
  agentCase: AgentCase;
  run?: CaseRun;
  drafts: IntegrationDraft[];
  loadError?: string;
  createIntentId: string;
  reviewIntentId: string;
  canCreate: boolean;
  canReview: boolean;
}) {
  if (loadError) {
    return <section className={styles.panelError} role="alert"><CircleAlert size={22} /><div><strong>Integration drafts could not be loaded.</strong><p>{loadError}</p></div></section>;
  }
  return (
    <div className={styles.workspacePanel}>
      <section className={styles.impactHeader}>
        <div>
          <p className={styles.sectionIndex}>Controlled integration boundary</p>
          <h2>{drafts.length} retained draft handoffs</h2>
          <p>Connectors can prepare case-bound content for review. They cannot send messages, publish pages, create tasks, or make quality-system decisions.</p>
        </div>
        <Send size={23} aria-hidden="true" />
      </section>
      {canCreate ? <IntegrationDraftForm caseId={agentCase.id} intentId={createIntentId} runId={run?.id} /> : null}
      {drafts.length ? (
        <ol className={styles.integrationList}>
          {drafts.map((draft) => (
            <li key={draft.id} data-status={draft.status.toLocaleLowerCase()}>
              <div className={styles.integrationHeading}>
                <div>
                  <span>{draft.channel} · {draft.status.replaceAll("_", " ")}</span>
                  <h3>{draft.content.title}</h3>
                  <small>Intended for {draft.destination} · requested by {draft.requestedBy}</small>
                </div>
                <strong>NOT SENT</strong>
              </div>
              <p className={styles.integrationBody}>{draft.content.body}</p>
              <HashField label="Immutable draft SHA-256" value={draft.contentSha256} />
              <p className={styles.immutabilityNote}><LockKeyhole size={14} /> Manual delivery required · external delivery allowed: false · {formatDate(draft.createdAt)}</p>
              {draft.reviewedBy ? <p className={styles.integrationReview}>Reviewed by {draft.reviewedBy}: {draft.reviewReason}</p> : null}
              {canReview && draft.status === "DRAFT" ? (
                <IntegrationDraftReviewForm caseId={agentCase.id} draft={draft} intentId={reviewIntentId} />
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <section className={styles.readOnlyNotice}>
          <LockKeyhole size={18} aria-hidden="true" />
          <div><strong>No handoff drafts recorded.</strong><p>Nothing has been sent or published from this case.</p></div>
        </section>
      )}
    </div>
  );
}

function EvidencePanel({ agentCase }: { agentCase: AgentCase }) {
  return (
    <div className={styles.workspacePanel}>
      <section className={styles.evidenceIntro}>
        <div>
          <p className={styles.sectionIndex}>Evidence explorer</p>
          <h2>Authoritative sources retained by version.</h2>
        </div>
        <div className={styles.trustLegend}>
          <span>A</span>
          <div><strong>Authoritative external evidence</strong><small>Official FDA document and retained source version</small></div>
        </div>
      </section>

      <ol className={styles.evidenceList}>
        {agentCase.sources.map((source, index) => (
          <li key={source.id}>
            <div className={styles.evidenceIndex}>A.{String(index + 1).padStart(2, "0")}</div>
            <article>
              <div className={styles.evidenceHeading}>
                <div>
                  <span>{source.sourceRole.replaceAll("_", " ")}</span>
                  <h3>FDA warning letter · retained version {source.documentVersionNumber}</h3>
                </div>
                <a href={source.sourceUrl} target="_blank" rel="noreferrer">
                  Official source <ArrowUpRight size={15} aria-hidden="true" />
                </a>
              </div>
              <dl className={styles.evidenceMeta}>
                <div><dt>Warning-letter ID</dt><dd><code>{source.warningLetterId}</code></dd></div>
                <div><dt>Document ID</dt><dd><code>{source.documentId}</code></dd></div>
                <div><dt>Document-version ID</dt><dd><code>{source.documentVersionId}</code></dd></div>
                <div><dt>Pinned by</dt><dd>{source.pinnedBy}</dd></div>
              </dl>
              <HashField label="Canonical source SHA-256" value={source.sourceSha256} />
              <p className={styles.immutabilityNote}><LockKeyhole size={14} aria-hidden="true" /> Immutable case input · pinned {formatDate(source.createdAt)}</p>
            </article>
          </li>
        ))}
      </ol>
    </div>
  );
}

function HistoryPanel({ events }: { events: CaseEvent[] }) {
  return (
    <div className={styles.workspacePanel}>
      <section className={styles.historyIntro}>
        <div>
          <p className={styles.sectionIndex}>Append-only trace</p>
          <h2>{events.length} attributable case events</h2>
        </div>
        <History size={22} aria-hidden="true" />
      </section>
      <ol className={styles.eventList}>
        {events.map((event) => (
          <li key={event.id}>
            <span className={styles.eventSequence}>{String(event.sequence).padStart(3, "0")}</span>
            <article>
              <div className={styles.eventHeading}>
                <div><span>{event.eventType.replaceAll("_", " ")}</span><strong>{payloadText(event)}</strong></div>
                <time dateTime={event.occurredAt}>{formatDate(event.occurredAt)}</time>
              </div>
              <dl className={styles.eventMeta}>
                <div><dt>Actor</dt><dd>{event.actorId} · {event.actorType}</dd></div>
                <div><dt>Request</dt><dd>{event.requestId}</dd></div>
                <div><dt>Prior event</dt><dd><code>{event.previousEventHash ? shortHash(event.previousEventHash, 7) : "GENESIS"}</code></dd></div>
                <div><dt>Event hash</dt><dd><code title={event.eventHash}>{shortHash(event.eventHash, 7)}</code></dd></div>
              </dl>
            </article>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function CaseWorkspace({
  agentCase,
  events,
  plan,
  run,
  runEvents,
  impact,
  verification,
  artifacts,
  integrationDrafts,
  activeView,
  planLoadError,
  runLoadError,
  impactLoadError,
  reviewLoadError,
  integrationLoadError,
  planIntentId,
  decisionIntentId,
  runIntentId,
  stepDecisionIntentId,
  impactIntentId,
  verificationIntentId,
  artifactIntentId,
  integrationIntentId,
  integrationReviewIntentId,
  canAuthorPlan,
  canDecidePlan,
  canControlRun,
  canDecideStep,
  canGenerateImpact,
  canReviewImpact,
  canRunVerification,
  canComposeArtifact,
  canReviewArtifact,
  canCreateIntegrationDraft,
  canReviewIntegrationDraft,
}: {
  agentCase: AgentCase;
  events: CaseEvent[];
  plan?: CasePlan;
  run?: CaseRun;
  runEvents: RunEvent[];
  impact?: ImpactMap;
  verification?: VerificationReport | null;
  artifacts: ArtifactVersion[];
  integrationDrafts: IntegrationDraft[];
  activeView: CaseWorkspaceView;
  planLoadError?: string;
  runLoadError?: string;
  impactLoadError?: string;
  reviewLoadError?: string;
  integrationLoadError?: string;
  planIntentId: string;
  decisionIntentId: string;
  runIntentId: string;
  stepDecisionIntentId: string;
  impactIntentId: string;
  verificationIntentId: string;
  artifactIntentId: string;
  integrationIntentId: string;
  integrationReviewIntentId: string;
  canAuthorPlan: boolean;
  canDecidePlan: boolean;
  canControlRun: boolean;
  canDecideStep: boolean;
  canGenerateImpact: boolean;
  canReviewImpact: boolean;
  canRunVerification: boolean;
  canComposeArtifact: boolean;
  canReviewArtifact: boolean;
  canCreateIntegrationDraft: boolean;
  canReviewIntegrationDraft: boolean;
}) {
  const source = agentCase.sources[0];
  return (
    <div className={styles.workspacePage}>
      <Link className={styles.backLink} href="/cases"><ArrowLeft size={15} aria-hidden="true" /> Case register</Link>
      <header className={styles.workspaceHeader}>
        <div className={styles.caseIdentity}>
          <span>CASE / {agentCase.id.slice(0, 8).toLocaleUpperCase()}</span>
          <h1>{agentCase.title}</h1>
          <p>{agentCase.objective}</p>
        </div>
        <div className={styles.caseState}>
          <span data-tone={caseStatusTone(agentCase.status)}>{formatCaseStatus(agentCase.status)}</span>
          <small>Updated {formatDate(agentCase.updatedAt)}</small>
        </div>
      </header>

      <nav className={styles.workspaceTabs} aria-label="Case workspace sections">
        {WORKSPACE_VIEWS.map((view, index) => (
          <Link
            key={view.id}
            href={`/cases/${agentCase.id}?view=${view.id}`}
            aria-current={activeView === view.id ? "page" : undefined}
            data-active={activeView === view.id}
          >
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{view.label}</strong>
            <small>{view.note}</small>
          </Link>
        ))}
      </nav>

      <div className={styles.workspaceGrid}>
        <main className={styles.workspaceMain}>
          {activeView === "overview" ? <OverviewPanel agentCase={agentCase} plan={plan} /> : null}
          {activeView === "plan" ? (
            <PlanPanel
              agentCase={agentCase}
              plan={plan}
              planLoadError={planLoadError}
              planIntentId={planIntentId}
              decisionIntentId={decisionIntentId}
              canAuthorPlan={canAuthorPlan}
              canDecidePlan={canDecidePlan}
            />
          ) : null}
          {activeView === "execution" ? (
            <ExecutionPanel
              agentCase={agentCase}
              plan={plan}
              run={run}
              runEvents={runEvents}
              runLoadError={runLoadError}
              runIntentId={runIntentId}
              stepDecisionIntentId={stepDecisionIntentId}
              canControlRun={canControlRun}
              canDecideStep={canDecideStep}
            />
          ) : null}
          {activeView === "impact" ? (
            <ImpactPanel
              agentCase={agentCase}
              impact={impact}
              impactLoadError={impactLoadError}
              impactIntentId={impactIntentId}
              canGenerateImpact={canGenerateImpact}
              canReviewImpact={canReviewImpact}
            />
          ) : null}
          {activeView === "review" ? (
            <ReviewPanel
              agentCase={agentCase}
              verification={verification}
              artifacts={artifacts}
              loadError={reviewLoadError}
              verificationIntentId={verificationIntentId}
              artifactIntentId={artifactIntentId}
              canRunVerification={canRunVerification}
              canComposeArtifact={canComposeArtifact}
              canReviewArtifact={canReviewArtifact}
            />
          ) : null}
          {activeView === "integrations" ? (
            <IntegrationsPanel
              agentCase={agentCase}
              run={run}
              drafts={integrationDrafts}
              loadError={integrationLoadError}
              createIntentId={integrationIntentId}
              reviewIntentId={integrationReviewIntentId}
              canCreate={canCreateIntegrationDraft}
              canReview={canReviewIntegrationDraft}
            />
          ) : null}
          {activeView === "evidence" ? <EvidencePanel agentCase={agentCase} /> : null}
          {activeView === "history" ? <HistoryPanel events={events} /> : null}
        </main>

        <aside className={styles.caseLedger} aria-label="Case control ledger">
          <div className={styles.ledgerHeading}>
            <FileText size={18} aria-hidden="true" />
            <div><span>Control ledger</span><strong>Current immutable references</strong></div>
          </div>
          <HashField label="Case state SHA-256" value={agentCase.currentStateHash} />
          {plan ? <HashField label={`Plan v${plan.version} SHA-256`} value={plan.planSha256} /> : null}
          {source ? <HashField label={`FDA source v${source.documentVersionNumber} SHA-256`} value={source.sourceSha256} /> : null}
          <dl className={styles.ledgerMeta}>
            <div><dt>Source count</dt><dd>{agentCase.sources.length}</dd></div>
            <div><dt>Event count</dt><dd>{events.length}</dd></div>
            <div><dt>Plan</dt><dd>{plan ? `v${plan.version}` : "Not created"}</dd></div>
            <div><dt>Approval</dt><dd>{plan ? formatCaseStatus(plan.approval.status) : "Not requested"}</dd></div>
            <div><dt>Run</dt><dd>{run ? formatCaseStatus(run.status) : "Not started"}</dd></div>
          </dl>
          <p className={styles.ledgerBoundary}>
            <ShieldCheck size={15} aria-hidden="true" />
            Execution is bounded and read-only. Controlled-system writes remain prohibited.
          </p>
        </aside>
      </div>
    </div>
  );
}
