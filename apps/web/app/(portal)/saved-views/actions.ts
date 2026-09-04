"use server";

import { revalidatePath } from "next/cache";
import {
  createSavedView,
  deleteSavedView,
  getLetter,
  getSavedViews,
  updateSavedView,
  type SavedViewMutationInput,
} from "@/lib/api-client";
import { requirePortalRole } from "@/lib/backend-auth";
import { bookmarkLetterId, bookmarkName } from "@/lib/letter-bookmarks";
import type { SavedView, SavedViewCriteria } from "@/lib/types";

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const CADENCES: SavedView["cadence"][] = ["Off", "Immediate", "Daily", "Weekly"];

function clean(value: string | undefined, maxLength: number) {
  return (value ?? "").trim().replace(/\s+/g, " ").slice(0, maxLength);
}

function normalizeCriteria(criteria: SavedViewCriteria): SavedViewCriteria {
  const postedFrom = clean(criteria.postedFrom, 10);
  const postedTo = clean(criteria.postedTo, 10);
  if (postedFrom && !DATE_PATTERN.test(postedFrom)) throw new Error("Invalid start date.");
  if (postedTo && !DATE_PATTERN.test(postedTo)) throw new Error("Invalid end date.");
  if (postedFrom && postedTo && postedFrom > postedTo) {
    throw new Error("The start date must be on or before the end date.");
  }
  return {
    query: clean(criteria.query, 300) || undefined,
    subtype: clean(criteria.subtype, 200) || undefined,
    category: clean(criteria.category, 300) || undefined,
    country: clean(criteria.country, 120) || undefined,
    lifecycle: criteria.lifecycle || undefined,
    review: criteria.review || undefined,
    document: criteria.document || undefined,
    postedFrom: postedFrom || undefined,
    postedTo: postedTo || undefined,
  };
}

function normalizeInput(input: SavedViewMutationInput): SavedViewMutationInput {
  const name = clean(input.name, 255);
  if (!name) throw new Error("A saved-view name is required.");
  if (!CADENCES.includes(input.cadence)) throw new Error("Unsupported alert cadence.");
  return {
    name,
    description: clean(input.description, 1_000),
    criteria: normalizeCriteria(input.criteria),
    cadence: input.cadence,
  };
}

export async function createSavedViewAction(input: SavedViewMutationInput) {
  await requirePortalRole("viewer");
  const result = await createSavedView(normalizeInput(input));
  revalidatePath("/saved-views");
  revalidatePath("/trends");
  return result;
}

export async function updateSavedViewAction(id: string, input: SavedViewMutationInput) {
  await requirePortalRole("viewer");
  const normalizedId = clean(id, 100);
  if (!normalizedId) throw new Error("A saved-view identifier is required.");
  const result = await updateSavedView(normalizedId, normalizeInput(input));
  revalidatePath("/saved-views");
  revalidatePath("/trends");
  return result;
}

export async function updateSavedViewCadenceAction(id: string, cadence: SavedView["cadence"]) {
  await requirePortalRole("viewer");
  const normalizedId = clean(id, 100);
  if (!normalizedId) throw new Error("A saved-view identifier is required.");
  if (!CADENCES.includes(cadence)) throw new Error("Unsupported alert cadence.");
  const result = await updateSavedView(normalizedId, { cadence });
  revalidatePath("/saved-views");
  revalidatePath("/trends");
  return result;
}

export async function deleteSavedViewAction(id: string) {
  await requirePortalRole("viewer");
  const normalizedId = clean(id, 100);
  if (!normalizedId) throw new Error("A saved-view identifier is required.");
  await deleteSavedView(normalizedId);
  revalidatePath("/saved-views");
  revalidatePath("/trends");
  return { deleted: true as const, id: normalizedId };
}

export async function setLetterBookmarkAction(letterId: string, shouldSave: boolean) {
  await requirePortalRole("viewer");
  const normalizedId = clean(letterId, 36);
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(normalizedId)) {
    throw new Error("A valid warning-letter identifier is required.");
  }

  const currentViews = await getSavedViews();
  const existing = currentViews.data.find((view) => bookmarkLetterId(view) === normalizedId);

  if (!shouldSave) {
    if (existing) await deleteSavedView(existing.id);
    revalidatePath("/saved-views");
    revalidatePath("/drug-letters");
    revalidatePath(`/drug-letters/${normalizedId}`);
    return { saved: false as const };
  }

  if (existing) return { saved: true as const, savedViewId: existing.id };

  const { data: letter } = await getLetter(normalizedId);
  if (!letter) throw new Error("The warning letter is no longer available.");

  const savedView = await createSavedView({
    name: bookmarkName(normalizedId),
    description: clean(`${letter.company} · ${letter.subject}`, 1_000),
    criteria: {
      query: clean(letter.marcsCms, 300) || clean(letter.company, 300),
    },
    cadence: "Off",
  });
  revalidatePath("/saved-views");
  revalidatePath("/drug-letters");
  revalidatePath(`/drug-letters/${normalizedId}`);
  return { saved: true as const, savedViewId: savedView.id };
}
