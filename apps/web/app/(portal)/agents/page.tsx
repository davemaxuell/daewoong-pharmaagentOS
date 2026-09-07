import type { Metadata } from "next";
import { AgentTeam } from "@/components/agent-platform/agent-team";

export const metadata: Metadata = { title: "Agent team · 에이전트 팀" };
export default function AgentsPage() { return <AgentTeam />; }
