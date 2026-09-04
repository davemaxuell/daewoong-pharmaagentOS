import { redirect } from "next/navigation";

type SearchParams = {
  letter?: string | string[];
  company?: string | string[];
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
  const destination = new URLSearchParams();
  const letter = firstValue(query.letter);
  const company = firstValue(query.company);

  if (letter) destination.set("letter", letter);
  if (company) destination.set("company", company);

  const suffix = destination.toString();
  redirect(suffix ? `/dashboard?${suffix}` : "/dashboard");
}
