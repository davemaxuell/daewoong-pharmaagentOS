import type { Metadata } from "next";
import Link from "next/link";
import { listApprovals, type ApprovalCenterItem } from "@/lib/governance-api-client";
import styles from "@/components/agent-platform/governance.module.css";

export const metadata: Metadata = { title: "Approval Center | PharmaAgent OS" };

function targetView(item: ApprovalCenterItem) {
  if (item.approvalType === "STEP_APPROVAL") return "execution";
  if (item.approvalType === "ARTIFACT_APPROVAL") return "review";
  return "plan";
}

export default async function ApprovalCenterPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const rawStatus = (await searchParams).status;
  const status = ["PENDING", "APPROVED", "REJECTED", "CANCELLED", "EXPIRED"].includes(rawStatus ?? "")
    ? rawStatus as ApprovalCenterItem["status"]
    : undefined;
  const approvals = await listApprovals(status).catch(() => null);
  if (!approvals) {
    return <main className={styles.page}><header><span>Approval Center</span><h1>Approval records are unavailable.</h1><p>Confirm the API connection and your case-review permission.</p></header></main>;
  }
  return (
    <main className={styles.page}>
      <header>
        <span>Approval Center / attributable decisions</span>
        <h1>Every human interrupt, in one bound queue.</h1>
        <p>Requests retain the exact case state, plan hash, target version, reviewer, and expiry. Decisions are completed in the corresponding case workspace.</p>
      </header>
      <nav className={styles.filters} aria-label="Approval filters">
        {[undefined, "PENDING", "APPROVED", "REJECTED", "CANCELLED", "EXPIRED"].map((item) => (
          <Link key={item ?? "ALL"} href={item ? `/approvals?status=${item}` : "/approvals"} data-active={status === item}>{item ?? "ALL"}</Link>
        ))}
      </nav>
      <section className={styles.section}>
        <div className={styles.sectionHeading}><div><span>Case-scoped requests</span><h2>{approvals.length} approval records</h2></div></div>
        <div className={styles.approvalList}>
          {approvals.map((item) => (
            <Link href={`/cases/${item.caseId}?view=${targetView(item)}`} key={item.id} className={styles.approvalCard} data-status={item.expired ? "expired" : item.status.toLocaleLowerCase()}>
              <div><span>{item.approvalType.replaceAll("_", " ")}</span><h3>{item.caseTitle}</h3><p>Plan v{item.planVersion} · requested by {item.requestedBy}</p></div>
              <strong>{item.expired ? "EXPIRED" : item.status}</strong>
              <code title={item.planSha256}>{item.planSha256.slice(0, 10)}…{item.planSha256.slice(-10)}</code>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
