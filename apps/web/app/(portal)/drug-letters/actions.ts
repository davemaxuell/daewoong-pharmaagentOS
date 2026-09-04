"use server";

import { generateLetterAiArtifact } from "@/lib/api-client";
import { requirePortalRole } from "@/lib/backend-auth";
import type { LetterAiArtifactLanguage, LetterAiArtifactType } from "@/lib/types";

export async function requestLetterAiArtifact(
  letterId: string,
  artifactType: LetterAiArtifactType,
  language: LetterAiArtifactLanguage = "ko",
) {
  await requirePortalRole("viewer");
  const normalizedId = letterId.trim();
  if (!normalizedId) throw new Error("A warning letter ID is required.");
  if (!(["translation", "findings", "summary"] as const).includes(artifactType)) {
    throw new Error("Unsupported warning-letter AI artifact type.");
  }
  if (!(language === "en" || language === "ko")) {
    throw new Error("Unsupported warning-letter AI artifact language.");
  }
  return generateLetterAiArtifact(normalizedId, artifactType, language);
}
