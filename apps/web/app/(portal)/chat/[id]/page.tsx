import { notFound } from "next/navigation";
import { ChatWorkspace } from "@/components/chat-workspace";
import { getChatLetter, getChatLetters, getChatThread } from "@/lib/api-client";

export default async function ChatPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [threadResult, letterResult] = await Promise.all([
    getChatThread(id),
    getChatLetters(),
  ]);
  if (threadResult.mode !== "live") {
    throw new Error(threadResult.detail || "Saved conversation service is unavailable.");
  }
  const thread = threadResult.data;
  if (!thread) notFound();

  const letters = [...letterResult.data];
  const missingLetterIds = thread.activeLetterIds.filter(
    (letterId) => !letters.some((letter) => letter.id === letterId),
  );
  const missingLetterResults = await Promise.all(missingLetterIds.map(getChatLetter));
  missingLetterResults.forEach((result) => {
    if (result.data && !letters.some((letter) => letter.id === result.data?.id)) {
      letters.push(result.data);
    }
  });

  const initialLetterId = thread.activeLetterIds.length === 1
    ? thread.activeLetterIds[0]
    : undefined;
  const initialLetter = letters.find((letter) => letter.id === initialLetterId);
  const lastMessage = thread.messages.at(-1);
  const conversationRevision = [
    thread.messages.length,
    lastMessage?.id ?? "empty",
    lastMessage?.status ?? "none",
    lastMessage?.updatedAt ?? lastMessage?.createdAt ?? "",
  ].join(":");
  return (
    <ChatWorkspace
      key={`${thread.id}:${conversationRevision}`}
      letters={letters}
      dataMode={letterResult.mode}
      initialLetterId={initialLetterId}
      initialCompany={initialLetter?.company}
      initialThread={thread}
      landingSeed={thread.id}
    />
  );
}
