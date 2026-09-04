import { PortalShell } from "@/components/portal-shell";
import { ChatHistoryProvider } from "@/components/chat-history-context";
import { getChatThreads, getNewLetterChanges } from "@/lib/api-client";
import { getPortalIdentity } from "@/lib/backend-auth";

export const dynamic = "force-dynamic";

export default async function PortalLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const [identity, threadResult, newLetterResult] = await Promise.all([
    getPortalIdentity(),
    getChatThreads({ limit: 100 }),
    getNewLetterChanges().catch(() => undefined),
  ]);
  const historyLoadState = threadResult.mode === "live"
    ? "ready"
    : threadResult.detail?.includes("API_BASE_URL is not configured")
      ? "preview"
      : "unavailable";
  const historyRevision = threadResult.data.items
    .map((thread) => `${thread.id}:${thread.updatedAt}`)
    .join("|");

  return (
    <ChatHistoryProvider
      key={`${historyLoadState}:${historyRevision}`}
      initialThreads={threadResult.data.items}
      initialLoadState={historyLoadState}
    >
      <PortalShell
        roles={identity.roles}
        newLetterNotification={{
          latestEventId: newLetterResult?.data[0]?.id,
          occurredAt: newLetterResult?.data[0]?.occurredAt,
        }}
        account={{
          name: identity.name,
          email: identity.email,
          image: identity.image,
          provider: identity.provider,
          authenticated: identity.authenticated,
        }}
      >
        {children}
      </PortalShell>
    </ChatHistoryProvider>
  );
}
