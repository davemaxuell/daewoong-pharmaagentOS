import type { SavedView } from "@/lib/types";

const BOOKMARK_PREFIX = "Drug letter bookmark:";
const LETTER_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function bookmarkName(letterId: string) {
  return `${BOOKMARK_PREFIX}${letterId}`;
}

export function bookmarkLetterId(view: Pick<SavedView, "name">) {
  if (!view.name.startsWith(BOOKMARK_PREFIX)) return undefined;
  const letterId = view.name.slice(BOOKMARK_PREFIX.length).trim();
  return LETTER_ID_PATTERN.test(letterId) ? letterId : undefined;
}

export function bookmarkedLetterIds(views: SavedView[]) {
  return views
    .map(bookmarkLetterId)
    .filter((letterId): letterId is string => Boolean(letterId));
}
