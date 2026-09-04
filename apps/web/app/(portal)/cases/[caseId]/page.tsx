import { randomUUID } from "node:crypto";
import type { Metadata } from "next";
import { CaseAccessState } from "@/components/agent-platform/case-index";
import { CaseWorkspace } from "@/components/agent-platform/case-workspace";
import {
  CaseApiError,
  getAgentCase,
  getAgentCaseArtifacts,
  getAgentCaseEvents,
  getAgentCaseImpact,
  getAgentCaseIntegrationDrafts,
  getAgentCaseVerification,
  getAgentCasePlan,
  getAgentCaseRun,
  getAgentCaseRunEvents,
} from "@/lib/case-api-client";
import { getPortalIdentity } from "@/lib/backend-auth";
import {
  isCaseWorkspaceView,
  isUuid,
  latestPlanVersion,
  latestRunId,
  type CaseRun,
  type ArtifactVersion,
  type ImpactMap,
  type IntegrationDraft,
  type RunEvent,
  type VerificationReport,
} from "@/lib/case-types";

export const metadata: Metadata = {
  title: "Case Workspace | PharmaAgent OS",
};

type SearchParams = { view?: string | string[] };

function firstValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function CaseWorkspacePage({
  params,
  searchParams,
}: {
  params: Promise<{ caseId: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { caseId } = await params;
  const requestedView = firstValue((await searchParams).view);
  const activeView = isCaseWorkspaceView(requestedView) ? requestedView : "overview";

  if (!isUuid(caseId)) return <CaseAccessState kind="not-found" />;
  const identity = await getPortalIdentity();

  let agentCase;
  let eventPage;
  try {
    [agentCase, eventPage] = await Promise.all([
      getAgentCase(caseId),
      getAgentCaseEvents(caseId),
    ]);
  } catch (error) {
    const kind = error instanceof CaseApiError && error.status === 403
      ? "forbidden"
      : error instanceof CaseApiError && error.status === 404
        ? "not-found"
        : "unavailable";
    return (
      <CaseAccessState
        kind={kind}
        requestId={error instanceof CaseApiError ? error.requestId : undefined}
      />
    );
  }

  const planVersion = latestPlanVersion(eventPage.items);
  let plan;
  let planLoadError: string | undefined;
  if (planVersion) {
    try {
      plan = await getAgentCasePlan(caseId, planVersion);
    } catch (error) {
      planLoadError = error instanceof CaseApiError && error.status === 403
        ? "Your role cannot inspect this plan version."
        : "The immutable plan reference exists, but its version could not be retrieved.";
    }
  }

  const runId = latestRunId(eventPage.items);
  let run: CaseRun | undefined;
  let runEvents: RunEvent[] = [];
  let runLoadError: string | undefined;
  if (runId) {
    try {
      const loaded = await Promise.all([
        getAgentCaseRun(runId),
        getAgentCaseRunEvents(runId),
      ]);
      [run, { items: runEvents }] = loaded;
    } catch (error) {
      runLoadError = error instanceof CaseApiError && error.status === 403
        ? "Your role cannot inspect this run."
        : "The run exists, but its current checkpoint or timeline could not be retrieved.";
    }
  }

  let impact: ImpactMap | undefined;
  let impactLoadError: string | undefined;
  if (activeView === "impact") {
    try {
      impact = await getAgentCaseImpact(caseId);
    } catch (error) {
      impactLoadError = error instanceof CaseApiError && error.status === 403
        ? "Your role cannot inspect internal impact records for this case."
        : "The current impact map could not be retrieved.";
    }
  }

  let verification: VerificationReport | null | undefined;
  let artifacts: ArtifactVersion[] = [];
  let reviewLoadError: string | undefined;
  if (activeView === "review") {
    try {
      const [loadedVerification, artifactPage] = await Promise.all([
        getAgentCaseVerification(caseId),
        getAgentCaseArtifacts(caseId),
      ]);
      verification = loadedVerification;
      artifacts = artifactPage.items;
    } catch (error) {
      reviewLoadError = error instanceof CaseApiError && error.status === 403
        ? "Your role cannot inspect QA review records for this case."
        : "Verification and artifact records could not be retrieved.";
    }
  }

  let integrationDrafts: IntegrationDraft[] = [];
  let integrationLoadError: string | undefined;
  if (activeView === "integrations") {
    try {
      integrationDrafts = (await getAgentCaseIntegrationDrafts(caseId)).items;
    } catch (error) {
      integrationLoadError = error instanceof CaseApiError && error.status === 403
        ? "Your role cannot inspect controlled integration drafts for this case."
        : "Controlled integration drafts could not be retrieved.";
    }
  }

  return (
    <CaseWorkspace
      agentCase={agentCase}
      events={eventPage.items}
      plan={plan}
      run={run}
      runEvents={runEvents}
      impact={impact}
      verification={verification}
      artifacts={artifacts}
      integrationDrafts={integrationDrafts}
      activeView={activeView}
      planLoadError={planLoadError}
      runLoadError={runLoadError}
      impactLoadError={impactLoadError}
      reviewLoadError={reviewLoadError}
      integrationLoadError={integrationLoadError}
      planIntentId={randomUUID()}
      decisionIntentId={randomUUID()}
      runIntentId={randomUUID()}
      stepDecisionIntentId={randomUUID()}
      impactIntentId={randomUUID()}
      verificationIntentId={randomUUID()}
      artifactIntentId={randomUUID()}
      integrationIntentId={randomUUID()}
      integrationReviewIntentId={randomUUID()}
      canAuthorPlan={identity.roles.includes("analyst") || identity.roles.includes("system_owner")}
      canDecidePlan={identity.roles.includes("reviewer")}
      canControlRun={identity.roles.includes("analyst") || identity.roles.includes("system_owner")}
      canDecideStep={identity.roles.includes("reviewer")}
      canGenerateImpact={identity.roles.includes("analyst") || identity.roles.includes("system_owner")}
      canReviewImpact={identity.roles.includes("reviewer") || identity.roles.includes("domain_sme")}
      canRunVerification={identity.roles.includes("analyst") || identity.roles.includes("system_owner")}
      canComposeArtifact={identity.roles.includes("analyst") || identity.roles.includes("system_owner")}
      canReviewArtifact={identity.roles.includes("reviewer")}
      canCreateIntegrationDraft={identity.roles.includes("analyst") || identity.roles.includes("system_owner")}
      canReviewIntegrationDraft={identity.roles.includes("reviewer") || identity.roles.includes("domain_sme")}
    />
  );
}
