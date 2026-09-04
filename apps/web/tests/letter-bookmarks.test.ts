import { describe, expect, it } from "vitest";
import { bookmarkedLetterIds, bookmarkLetterId, bookmarkName } from "@/lib/letter-bookmarks";
import type { SavedView } from "@/lib/types";

function savedView(name: string): SavedView {
  return {
    id: "view-id",
    name,
    description: "",
    criteria: {},
    filters: [],
    cadence: "Off",
    alertState: "off",
    resultCount: 0,
    lastMatched: "",
    owner: "You",
    openUrl: "/drug-letters",
    updatedAt: "2026-09-04T00:00:00Z",
  };
}

describe("letter bookmark markers", () => {
  it("round-trips a warning-letter id", () => {
    const letterId = "46a0f98b-2271-4df3-9c22-36d9d77a60ee";
    expect(bookmarkLetterId(savedView(bookmarkName(letterId)))).toBe(letterId);
  });

  it("ignores legacy saved monitoring views and invalid markers", () => {
    expect(bookmarkLetterId(savedView("Quality Unit monitoring"))).toBeUndefined();
    expect(bookmarkLetterId(savedView("Drug letter bookmark:not-an-id"))).toBeUndefined();
  });

  it("extracts only letter bookmarks from a mixed saved-view list", () => {
    const letterId = "46a0f98b-2271-4df3-9c22-36d9d77a60ee";
    expect(bookmarkedLetterIds([
      savedView("Legacy filter"),
      savedView(bookmarkName(letterId)),
    ])).toEqual([letterId]);
  });
});
