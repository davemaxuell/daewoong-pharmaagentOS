import { getChatThreads, getNewLetterChanges } from "@/lib/api-client";
import { requirePortalRole } from "@/lib/backend-auth";

export async function GET() {
  await requirePortalRole("viewer");
  const [history, changes] = await Promise.all([
    getChatThreads({ limit: 100 }),
    getNewLetterChanges(1).catch(() => undefined),
  ]);
  return Response.json({
    threads: history.data.items,
    historyLoadState: history.mode === "live" ? "ready"
      : history.detail?.includes("API_BASE_URL is not configured") ? "preview" : "unavailable",
    notification: {
      latestEventId: changes?.data[0]?.id,
      occurredAt: changes?.data[0]?.occurredAt,
    },
  }, { headers: { "Cache-Control": "private, no-store" } });
}
