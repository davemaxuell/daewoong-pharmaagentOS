import { AgentHome } from "@/components/agent-platform/agent-home";
import { CaseApiError, listAgentCases } from "@/lib/case-api-client";

export default async function RequestsPage() {
  let page;
  try {
    page = await listAgentCases();
  } catch (error) {
    return <AgentHome cases={null} access={error instanceof CaseApiError && error.status === 403 ? "restricted" : "unavailable"} />;
  }
  return <AgentHome cases={page.items} access="ready" />;
}
