import { randomUUID } from "node:crypto";
import { redirect } from "next/navigation";
import { ChatWorkspace } from "@/components/chat-workspace";
import { getChatLetter, getChatLetters } from "@/lib/api-client";

type SearchParams = {
  letter?: string | string[];
  company?: string | string[];
  new?: string | string[];
};

function firstValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function AskPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const query = await searchParams;
  const initialLetterId = firstValue(query.letter);
  const initialCompany = firstValue(query.company);
  const landingSeed = firstValue(query.new)?.slice(0, 128);

  if (!landingSeed) {
    const destination = new URLSearchParams();
    if (initialLetterId) destination.set("letter", initialLetterId);
    if (initialCompany) destination.set("company", initialCompany);
    destination.set("new", randomUUID());
    redirect(`/ask?${destination.toString()}`);
  }

  const [letterResult, constrainedLetterResult] = await Promise.all([
    getChatLetters(),
    initialLetterId ? getChatLetter(initialLetterId) : Promise.resolve(undefined),
  ]);
  const letters = [...letterResult.data];
  const constrainedLetter = constrainedLetterResult?.data;
  if (constrainedLetter && !letters.some((letter) => letter.id === constrainedLetter.id)) {
    letters.push(constrainedLetter);
  }

  return (
    <ChatWorkspace
      key={landingSeed}
      letters={letters}
      dataMode={letterResult.mode}
      initialLetterId={initialLetterId}
      initialCompany={initialCompany}
      landingSeed={landingSeed}
    />
  );
}
