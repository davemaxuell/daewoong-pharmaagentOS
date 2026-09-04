import type { Metadata } from "next";
import { SavedLettersWorkspace, type SavedLetterEntry } from "@/components/saved-views-workspace";
import { getLetters, getSavedViews } from "@/lib/api-client";
import { bookmarkLetterId } from "@/lib/letter-bookmarks";

export const metadata: Metadata = { title: "저장된 경고서한 | Saved Drug Letters" };

export default async function SavedViewsPage() {
  const [letterResult, savedViewResult] = await Promise.all([getLetters(), getSavedViews()]);
  const lettersById = new Map(letterResult.data.map((letter) => [letter.id, letter]));
  const entries = savedViewResult.data.reduce<SavedLetterEntry[]>((saved, view) => {
    const letterId = bookmarkLetterId(view);
    const letter = letterId ? lettersById.get(letterId) : undefined;
    if (letter) saved.push({ letter, savedAt: view.updatedAt });
    return saved;
  }, []);
  const mode = letterResult.mode === "live" && savedViewResult.mode === "live" ? "live" : "seeded";

  return <SavedLettersWorkspace initialEntries={entries} mode={mode} />;
}
