import type { ChatThreadSummary } from "@/lib/types";

/** Late sidebar reads must not undo a newly created, updated or archived chat. */
export function mergeChatHistory(
  current: ChatThreadSummary[],
  incoming: ChatThreadSummary[],
  changedIds: ReadonlySet<string>,
): ChatThreadSummary[] {
  const merged = new Map(incoming.filter((item) => !changedIds.has(item.id)).map((item) => [item.id, item]));
  for (const item of current) {
    if (changedIds.has(item.id)) merged.set(item.id, item);
  }
  return [...merged.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}
