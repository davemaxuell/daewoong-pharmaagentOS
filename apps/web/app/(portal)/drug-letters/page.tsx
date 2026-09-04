import type { Metadata } from "next";
import { getLetters, getSavedViews } from "@/lib/api-client";
import { LettersExplorer, type LetterExplorerInitialState } from "@/components/letters-explorer";
import { bookmarkedLetterIds } from "@/lib/letter-bookmarks";

export const metadata: Metadata = { title: "의약품 경고서한 | Drug Letters" };

function first(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function DrugLettersPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const [{ data, mode }, savedViews] = await Promise.all([getLetters(), getSavedViews()]);
  const requestedPageSize = Number(first(params.pageSize));
  const requestedPage = Number(first(params.page));
  const requestedSort = first(params.sort);
  const allowedSorts = new Set(["posted-desc", "posted-asc", "issued-desc", "company-asc"]);
  const initialState: LetterExplorerInitialState = {
    filters: {
      query: first(params.q),
      subtype: first(params.subtype),
      category: first(params.category),
      country: first(params.country),
      lifecycle: first(params.lifecycle),
      review: first(params.review),
      document: first(params.document),
      postedFrom: first(params.postedFrom),
      postedTo: first(params.postedTo),
    },
    page: Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1,
    pageSize: [20, 50, 100].includes(requestedPageSize) ? requestedPageSize : 20,
    sort: allowedSorts.has(requestedSort)
      ? requestedSort as LetterExplorerInitialState["sort"]
      : "posted-desc",
  };

  return (
    <LettersExplorer
      initialLetters={data}
      initialSavedLetterIds={bookmarkedLetterIds(savedViews.data)}
      mode={mode}
      initialState={initialState}
    />
  );
}
