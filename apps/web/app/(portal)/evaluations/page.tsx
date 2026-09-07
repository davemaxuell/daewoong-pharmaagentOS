import { ServiceState } from "@/components/agent-platform/service-state";
import type { Metadata } from "next";
import { ReleaseForm, RunForm, SuiteForm } from "@/components/agent-platform/evaluation-forms";
import { getPortalIdentity } from "@/lib/backend-auth";
import {
  listEvaluationRuns,
  listEvaluationSuites,
  listGovernanceInventory,
} from "@/lib/governance-api-client";
import styles from "@/components/agent-platform/governance.module.css";

export const metadata: Metadata = { title: "Evaluation Center | PharmaAgent OS" };

export default async function EvaluationCenterPage() {
  const identity = await getPortalIdentity();
  let data;
  try {
    data = await Promise.all([listEvaluationSuites(), listEvaluationRuns(), listGovernanceInventory()]);
  } catch {
    return <ServiceState surface="evaluations" />;
  }
  const [suites, runs, inventory] = data;
  const canDevelop = identity.roles.includes("agent_developer") || identity.roles.includes("system_owner");
  const canRelease = identity.roles.includes("system_owner");
  return (
    <div className={styles.page}>
      <header><span>Evaluation Center / outcome assurance</span><h1>Release the record, not the claim.</h1><p>Every candidate is bound to an immutable hash, run at least three times, graded against actual final state, and blocked on critical regression.</p></header>
      {canDevelop ? <section className={styles.formGrid}><SuiteForm /><RunForm suites={suites} inventory={inventory} /></section> : null}
      <section className={styles.section}><div className={styles.sectionHeading}><div><span>Versioned suites</span><h2>{suites.length} qualification definitions</h2></div></div><div className={styles.cardGrid}>{suites.map((suite) => <article className={styles.card} key={suite.id}><span>{suite.targetKind.replaceAll("_", " ")}</span><h3>{suite.name}</h3><p>{suite.suiteKey}@{suite.version} · {suite.caseCount} cases</p><code title={suite.suiteSha256}>{suite.suiteSha256.slice(0, 12)}…{suite.suiteSha256.slice(-12)}</code></article>)}</div></section>
      <section className={styles.section}><div className={styles.sectionHeading}><div><span>Trial history</span><h2>{runs.length} evaluation runs</h2></div></div><div className={styles.runList}>{runs.map((run) => <article className={styles.run} key={run.id} data-status={run.status.toLowerCase()}><div><span>{run.targetKind.replaceAll("_", " ")}</span><h3>{run.status} · {run.passedTrials}/{run.totalTrials} trials</h3><p>{run.criticalFailures} critical failures · ${run.totalCostUsd.toFixed(4)} · {run.totalLatencyMs}ms</p></div><dl><div><dt>Pass rate</dt><dd>{Math.round(Number(run.metrics.pass_rate ?? 0) * 100)}%</dd></div><div><dt>Trajectory events</dt><dd>{run.trials.reduce((sum, trial) => sum + trial.trajectory.length, 0)}</dd></div></dl><code title={run.targetSha256}>{run.targetSha256.slice(0, 10)}…{run.targetSha256.slice(-10)}</code>{canRelease ? <ReleaseForm run={run} /> : null}</article>)}</div></section>
    </div>
  );
}
