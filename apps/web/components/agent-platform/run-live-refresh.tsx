"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import type { AgentRunStatus } from "@/lib/case-types";

export function RunLiveRefresh({ status }: { status: AgentRunStatus }) {
  const router = useRouter();
  useEffect(() => {
    if (!["PENDING", "RUNNING", "WAITING_FOR_APPROVAL"].includes(status)) return;
    const timer = window.setInterval(() => router.refresh(), 2_000);
    return () => window.clearInterval(timer);
  }, [router, status]);
  return null;
}
