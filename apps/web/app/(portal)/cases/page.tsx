import { randomUUID } from "node:crypto";
import type { Metadata } from "next";
import { CaseAccessState, CaseIndex } from "@/components/agent-platform/case-index";
import { CaseApiError, listAgentCases } from "@/lib/case-api-client";
import { getPortalIdentity } from "@/lib/backend-auth";
import { CASE_STATUSES, type CaseStatus } from "@/lib/case-types";

export const metadata: Metadata = {
  title: "Regulatory Cases | PharmaAgent OS",
  description: "Version-bound regulatory impact review cases and their approval history.",
};

type SearchParams = { status?: string | string[] };

function firstValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function caseStatus(value: string | undefined): CaseStatus | undefined {
  return value && (CASE_STATUSES as readonly string[]).includes(value)
    ? value as CaseStatus
    : undefined;
}

export default async function CasesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const status = caseStatus(firstValue((await searchParams).status));
  const identity = await getPortalIdentity();
  let page;
  try {
    page = await listAgentCases(status);
  } catch (error) {
    if (error instanceof CaseApiError && error.status === 403) {
      return <CaseAccessState kind="forbidden" requestId={error.requestId} />;
    }
    return (
      <CaseAccessState
        kind="unavailable"
        requestId={error instanceof CaseApiError ? error.requestId : undefined}
      />
    );
  }
  return (
    <CaseIndex
      page={page}
      activeStatus={status}
      intentId={randomUUID()}
      canCreate={identity.roles.includes("analyst") || identity.roles.includes("system_owner")}
    />
  );
}
