"use server";

import {
  getReviewQueue,
  updateReview,
  type ReviewQueueFilter,
} from "@/lib/api-client";
import { requirePortalRole } from "@/lib/backend-auth";
import type { ReviewState } from "@/lib/types";

export async function submitReviewDecision(
  summaryId: string,
  state: ReviewState,
  reason: string,
  editedFinding: string | undefined,
  expectedVersion: string,
) {
  await requirePortalRole("reviewer");
  const normalizedReason = reason.trim().slice(0, 2000);
  const normalizedFinding = editedFinding?.trim();
  if (normalizedReason.length < 8) throw new Error("A specific review reason is required for an attributable decision.");
  if (!(["approved", "needs_revision", "rejected"] as ReviewState[]).includes(state)) throw new Error("Unsupported review decision.");
  if (normalizedFinding !== undefined && normalizedFinding.length < 10) {
    throw new Error("Edited review output must contain at least 10 characters.");
  }
  if (normalizedFinding !== undefined && state !== "approved") {
    throw new Error("Edited output may only be approved as a new version.");
  }
  return updateReview(summaryId, state, normalizedReason, {
    editedFinding: normalizedFinding,
    expectedVersion,
  });
}

export async function refreshReviewQueue(input: {
  view: ReviewQueueFilter;
  cursor?: string;
  pageSize?: number;
}) {
  await requirePortalRole("reviewer");
  return getReviewQueue(input);
}
