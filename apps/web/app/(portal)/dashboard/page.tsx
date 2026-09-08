import { redirect } from "next/navigation";
import { BeginnerHome } from "@/components/agent-platform/beginner-home";

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
  return <BeginnerHome />;
}
