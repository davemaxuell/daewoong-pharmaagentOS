import Link from "next/link";
import { ServiceState } from "./service-state";
import { ArrowRight, BriefcaseBusiness, LockKeyhole } from "lucide-react";
import { CreateCaseForm } from "@/components/agent-platform/case-forms";
import {
  CASE_STATUSES,
  caseStatusTone,
  formatCaseStatus,
  shortHash,
  type AgentCasePage,
  type CaseStatus,
} from "@/lib/case-types";
import styles from "./case-workbench.module.css";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function CaseAccessState({
  kind,
  requestId,
}: {
  kind: "forbidden" | "unavailable" | "not-found";
  requestId?: string;
}) {
  if (kind !== "not-found") return <ServiceState surface="cases" restricted={kind === "forbidden"} requestId={requestId} />;
  return <section className={styles.accessState}><h1>Case not found</h1><p>This case is not available in the current scope.</p><Link href="/dashboard">Return to agent workspace</Link></section>;
}

const FILTERS: Array<{ label: string; status?: CaseStatus }> = [
  { label: "All records" },
  { label: "Draft", status: "DRAFT" },
  { label: "Plan review", status: "AWAITING_PLAN_APPROVAL" },
  { label: "Ready", status: "READY" },
  { label: "Needs revision", status: "NEEDS_REVISION" },
  { label: "Completed", status: "COMPLETED" },
];

export function CaseIndex({
  page,
  activeStatus,
  intentId,
  canCreate,
}: {
  page: AgentCasePage;
  activeStatus?: CaseStatus;
  intentId: string;
  canCreate: boolean;
}) {
  return (
    <div className={styles.indexPage}>
      <header className={styles.indexHeader}>
        <div>
          <p className={styles.eyebrow}>PharmaAgent OS · governed work</p>
          <h1>Regulatory cases</h1>
          <p className={styles.lede}>
            Convert one retained FDA source version into an inspectable plan, evidence trail, and independent decision.
          </p>
        </div>
        <div className={styles.headerControl}>
          <LockKeyhole size={16} aria-hidden="true" />
          <span>Append-only history</span>
          <strong>Exact-version evidence</strong>
        </div>
      </header>

      <section className={styles.boundaryStrip} aria-label="Case boundary">
        <span>Decision support only</span>
        <p>
          The workspace cannot declare noncompliance, open a CAPA, alter an SOP, or write to controlled QMS, EDMS, MES, or LIMS records.
        </p>
      </section>

      <div className={styles.indexGrid}>
        <section className={styles.caseRegister} aria-labelledby="case-register-title">
          <div className={styles.registerHeading}>
            <div>
              <span>Case register</span>
              <h2 id="case-register-title">{page.items.length} governed records</h2>
            </div>
            <BriefcaseBusiness size={22} aria-hidden="true" />
          </div>

          <nav className={styles.filters} aria-label="Filter cases by state">
            {FILTERS.map((filter) => {
              const active = filter.status === activeStatus || (!filter.status && !activeStatus);
              return (
                <Link
                  key={filter.label}
                  href={filter.status ? `/cases?status=${filter.status}` : "/cases"}
                  aria-current={active ? "page" : undefined}
                  data-active={active}
                >
                  {filter.label}
                </Link>
              );
            })}
          </nav>

          {page.items.length ? (
            <ol className={styles.caseList}>
              {page.items.map((item, index) => {
                const source = item.sources[0];
                return (
                  <li key={item.id}>
                    <Link className={styles.caseRow} href={`/cases/${item.id}`}>
                      <span className={styles.caseOrdinal}>{String(index + 1).padStart(2, "0")}</span>
                      <span className={styles.caseSummary}>
                        <span className={styles.caseKicker}>
                          <span data-tone={caseStatusTone(item.status)}>{formatCaseStatus(item.status)}</span>
                          <span>{item.workflowKey}</span>
                        </span>
                        <strong>{item.title}</strong>
                        <small>{item.objective}</small>
                      </span>
                      <span className={styles.caseMeta}>
                        <span>Updated {formatDate(item.updatedAt)}</span>
                        <code title={item.currentStateHash}>{shortHash(item.currentStateHash, 6)}</code>
                        {source ? <small>FDA source v{source.documentVersionNumber}</small> : null}
                      </span>
                      <ArrowRight size={18} aria-hidden="true" />
                    </Link>
                  </li>
                );
              })}
            </ol>
          ) : (
            <div className={styles.emptyRegister}>
              <span aria-hidden="true">00</span>
              <h3>No cases match this register view.</h3>
              <p>Open a case from one admitted Drug warning-letter version to establish the first immutable evidence pin.</p>
            </div>
          )}

          {page.hasMore ? (
            <p className={styles.paginationNote}>The first 100 records are shown. Narrow the register by state to continue.</p>
          ) : null}
        </section>

        <aside className={styles.intakeRail} aria-label="Open a governed case">
          {canCreate ? (
            <CreateCaseForm intentId={intentId} />
          ) : (
            <section className={styles.readOnlyIntake}>
              <LockKeyhole size={19} aria-hidden="true" />
              <span>Read-only case access</span>
              <h2>New-case intake is role controlled.</h2>
              <p>Regulatory Analyst or System Owner authority is required to establish a case and pin an FDA source version.</p>
            </section>
          )}
          <div className={styles.roleNote}>
            <span>Creation authority</span>
            <p>Requires Regulatory Analyst or System Owner. Source scope and exact version are revalidated by the API.</p>
          </div>
        </aside>
      </div>

      <span className={styles.statusReference} aria-hidden="true">
        Supported states: {CASE_STATUSES.join(" · ")}
      </span>
    </div>
  );
}
