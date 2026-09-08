import { Suspense } from "react";
import { ResearchWorkspace } from "@/components/research/research-workspace";

export const metadata = { title: "FDA Research Agent · FDA 리서치 에이전트" };

export default function ResearchPage() {
  return <Suspense fallback={<p role="status">Loading research… · 리서치를 불러오고 있어요…</p>}><ResearchWorkspace /></Suspense>;
}
