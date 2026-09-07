import { ApiRequestError, generateLetterAiArtifact } from "@/lib/api-client";
import { getPortalIdentity } from "@/lib/backend-auth";
import type { LetterAiArtifactLanguage, LetterAiArtifactType } from "@/lib/types";

export const runtime = "nodejs";
// Vercel Hobby caps functions at 300 seconds. The upstream API still enforces
// its shorter document-generation timeout and returns a controlled failure.
export const maxDuration = 300;

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ARTIFACT_TYPES = new Set<LetterAiArtifactType>(["translation", "findings", "summary"]);
const LANGUAGES = new Set<LetterAiArtifactLanguage>(["en", "ko"]);

function hasSameRequestOrigin(request: Request) {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    const originUrl = new URL(origin);
    const requestUrl = new URL(request.url);
    const allowedOrigins = new Set([requestUrl.origin]);
    const host = request.headers.get("host")?.split(",")[0]?.trim();
    const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
    const forwardedProtocol = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
    const requestProtocol = requestUrl.protocol.replace(":", "");

    for (const [candidateHost, candidateProtocol] of [
      [host, requestProtocol],
      [forwardedHost, forwardedProtocol || requestProtocol],
    ] as const) {
      if (!candidateHost || !candidateProtocol) continue;
      try {
        allowedOrigins.add(new URL(`${candidateProtocol}://${candidateHost}`).origin);
      } catch {
        // Malformed proxy headers never expand the origin allowlist.
      }
    }
    return allowedOrigins.has(originUrl.origin);
  } catch {
    return false;
  }
}

type RouteParameters = {
  params: Promise<{ id: string; artifactType: string }>;
};

export async function POST(request: Request, { params }: RouteParameters) {
  await getPortalIdentity();

  if (!hasSameRequestOrigin(request)) {
    return Response.json({ error: "Cross-origin generation requests are not allowed." }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return Response.json({ error: "A JSON request body is required." }, { status: 415 });
  }

  const { id, artifactType: rawArtifactType } = await params;
  if (!UUID_PATTERN.test(id) || !ARTIFACT_TYPES.has(rawArtifactType as LetterAiArtifactType)) {
    return Response.json({ error: "The requested Drug Letter artifact is invalid." }, { status: 422 });
  }

  let language: LetterAiArtifactLanguage;
  try {
    const body = await request.json() as { language?: unknown };
    language = String(body.language) as LetterAiArtifactLanguage;
  } catch {
    return Response.json({ error: "The generation request body is invalid." }, { status: 400 });
  }
  const artifactType = rawArtifactType as LetterAiArtifactType;
  if (!LANGUAGES.has(language) || (artifactType === "translation" && language !== "ko")) {
    return Response.json({ error: "The requested artifact language is not supported." }, { status: 422 });
  }

  try {
    const artifact = await generateLetterAiArtifact(id, artifactType, language);
    return Response.json(artifact, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const status = error instanceof ApiRequestError ? error.status : 502;
    const requestId = error instanceof ApiRequestError ? error.requestId : undefined;
    console.error(
      "Drug Letter artifact proxy failed",
      `status=${status}`,
      requestId ? `request_id=${requestId}` : "request_id=unavailable",
    );
    const message = status === 429
      ? "Generation is temporarily busy. Please retry shortly."
      : status === 503
        ? "Document AI generation is not currently available."
        : "The validated AI result could not be completed.";
    return Response.json(
      { error: message, requestId },
      { status, headers: { "Cache-Control": "no-store" } },
    );
  }
}
