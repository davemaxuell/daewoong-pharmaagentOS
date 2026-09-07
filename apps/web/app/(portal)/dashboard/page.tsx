import { redirect } from "next/navigation";
import { AgentHome } from "@/components/agent-platform/agent-home";
import { CaseApiError, listAgentCases } from "@/lib/case-api-client";

export default async function DashboardPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  // Preserve old deep links to letter-constrained research and new conversations.
  if (query.letter || query.company || query.new) {
    const destination = new URLSearchParams();
    for (const key of ["letter", "company", "new"]) {
      const value = query[key];
      if (value) destination.set(key, Array.isArray(value) ? value[0] : value);
    }
    redirect(`/ask?${destination.toString()}`);
  }
  let page;
  try {
    page = await listAgentCases();
  } catch (error) {
    return <AgentHome cases={null} access={error instanceof CaseApiError && error.status === 403 ? "restricted" : "unavailable"} />;
  }
  return <AgentHome cases={page.items} access="ready" />;
}
