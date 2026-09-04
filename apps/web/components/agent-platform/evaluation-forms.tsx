"use client";

import { useActionState } from "react";
import {
  approveReleaseAction,
  createStandardSuiteAction,
  EMPTY_EVALUATION_ACTION_STATE,
  runSuiteAction,
} from "@/app/(portal)/evaluations/actions";
import type { EvaluationRun, EvaluationSuite, InventoryItem } from "@/lib/governance-api-client";
import styles from "./governance.module.css";

function State({ state }: { state: typeof EMPTY_EVALUATION_ACTION_STATE }) {
  return state.status === "idle" ? null : <p className={state.status === "error" ? styles.error : styles.success}>{state.message}</p>;
}

export function SuiteForm() {
  const [state, action, pending] = useActionState(createStandardSuiteAction, EMPTY_EVALUATION_ACTION_STATE);
  return <form className={styles.form} action={action}><h2>Create a qualification suite</h2><label>Suite key<input name="suite_key" placeholder="verification-release-2026" pattern="[a-z][a-z0-9-]+" required /></label><label>Target kind<select name="target_kind"><option value="AGENT_VERSION">Agent version</option><option value="WORKFLOW_VERSION">Workflow version</option></select></label><button disabled={pending}>{pending ? "Creating…" : "Create immutable suite"}</button><State state={state} /></form>;
}

export function RunForm({ suites, inventory }: { suites: EvaluationSuite[]; inventory: InventoryItem[] }) {
  const [state, action, pending] = useActionState(runSuiteAction, EMPTY_EVALUATION_ACTION_STATE);
  return <form className={styles.form} action={action}><h2>Run three trials</h2><label>Suite<select name="suite_id" required>{suites.map((suite) => <option key={suite.id} value={suite.id}>{suite.suiteKey}@{suite.version}</option>)}</select></label><label>Exact target<select name="target_version_id" required>{inventory.filter((item) => item.kind === "AGENT_VERSION" || item.kind === "WORKFLOW_VERSION").map((item) => <option key={item.id} value={item.id} data-kind={item.kind}>{item.key}@{item.version} · {item.releaseStatus}</option>)}</select></label><label>Target kind<select name="target_kind"><option value="AGENT_VERSION">Agent version</option><option value="WORKFLOW_VERSION">Workflow version</option></select></label><button disabled={pending || !suites.length}>{pending ? "Running…" : "Execute evaluation"}</button><State state={state} /></form>;
}

export function ReleaseForm({ run }: { run: EvaluationRun }) {
  const [state, action, pending] = useActionState(approveReleaseAction, EMPTY_EVALUATION_ACTION_STATE);
  return <form className={styles.releaseForm} action={action}><input type="hidden" name="run_id" value={run.id} /><input type="hidden" name="target_sha256" value={run.targetSha256} /><select name="target_status" aria-label="Release environment"><option value="STAGING">Staging</option><option value="PRODUCTION">Production</option></select><input name="reason" minLength={8} maxLength={2_000} placeholder="Release rationale" required /><button disabled={pending || run.status !== "PASSED"}>{pending ? "Recording…" : "Approve release"}</button><State state={state} /></form>;
}
