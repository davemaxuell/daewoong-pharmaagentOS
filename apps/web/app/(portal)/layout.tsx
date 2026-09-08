import { PortalShell } from "@/components/portal-shell";
import { ChatHistoryProvider } from "@/components/chat-history-context";
import { getPortalIdentity } from "@/lib/backend-auth";

export const dynamic = "force-dynamic";

export default async function PortalLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Identity is local to the signed browser session. Sidebar network reads must
  // not block every route or remount the conversation while an answer is streaming.
  const identity = await getPortalIdentity();

  return (
    <ChatHistoryProvider
      key={identity.subject}
      initialThreads={[]}
      initialLoadState="loading"
    >
      <PortalShell
        roles={identity.roles}
        newLetterNotification={{}}
      >
        {children}
      </PortalShell>
    </ChatHistoryProvider>
  );
}
