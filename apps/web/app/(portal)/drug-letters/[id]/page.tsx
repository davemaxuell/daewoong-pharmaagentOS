import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { LetterDetail } from "@/components/letter-detail";
import { getLetter, getSavedViews } from "@/lib/api-client";
import { bookmarkedLetterIds } from "@/lib/letter-bookmarks";

export const maxDuration = 300;

type PageProps = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const { data } = await getLetter(id);
  return { title: data ? `${data.company} · ${data.marcsCms}` : "의약품 경고서한을 이용할 수 없음 | Drug letter unavailable" };
}

export default async function DrugLetterDetailPage({ params }: PageProps) {
  const { id } = await params;
  const [{ data: letter }, savedViews] = await Promise.all([getLetter(id), getSavedViews()]);
  if (!letter) notFound();
  return <LetterDetail letter={letter} initiallySaved={bookmarkedLetterIds(savedViews.data).includes(id)} />;
}
