"use server";

import { requestCorpusSync, requestReprocess, updateNotificationSettings } from "@/lib/api-client";
import { requirePortalRole } from "@/lib/backend-auth";

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export async function saveNotificationSettings(targetEmail: string, enabled: boolean) {
  await requirePortalRole("admin");
  const normalizedEmail = targetEmail.trim().slice(0, 320);
  if (!EMAIL_PATTERN.test(normalizedEmail)) {
    throw new Error("A valid notification email is required.");
  }
  return updateNotificationSettings(normalizedEmail, enabled);
}

export async function submitReprocess(letterId: string, reason: string) {
  await requirePortalRole("admin");
  const normalizedId = letterId.trim().slice(0, 200);
  const normalizedReason = reason.trim().slice(0, 2000);
  if (!normalizedId) throw new Error("A letter identifier is required.");
  if (normalizedReason.length < 8) throw new Error("A specific operational reason is required.");
  return requestReprocess(normalizedId, normalizedReason);
}

export async function startCorpusSync() {
  await requirePortalRole("admin");
  return requestCorpusSync();
}
