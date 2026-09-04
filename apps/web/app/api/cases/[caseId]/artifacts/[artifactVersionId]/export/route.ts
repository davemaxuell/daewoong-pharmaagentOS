import { getAuthenticatedPortalIdentity, getBackendBearerAssertion } from "@/lib/backend-auth";

export const runtime = "nodejs";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ caseId: string; artifactVersionId: string }> },
) {
  const identity = await getAuthenticatedPortalIdentity();
  if (!identity) return Response.json({ error: "Authentication is required." }, { status: 401 });
  const { caseId, artifactVersionId } = await params;
  if (!UUID_PATTERN.test(caseId) || !UUID_PATTERN.test(artifactVersionId)) {
    return Response.json({ error: "Artifact reference is invalid." }, { status: 422 });
  }
  const origin = process.env.API_BASE_URL?.replace(/\/$/, "");
  if (!origin) return Response.json({ error: "The case service is not configured." }, { status: 503 });
  const assertion = await getBackendBearerAssertion();
  const upstream = await fetch(
    `${origin}/api/v1/cases/${encodeURIComponent(caseId)}/artifacts/${encodeURIComponent(artifactVersionId)}/export`,
    { headers: { Authorization: `Bearer ${assertion}` }, cache: "no-store" },
  );
  if (!upstream.ok) {
    return Response.json({ error: "The approved artifact is not available." }, { status: upstream.status });
  }
  return new Response(await upstream.arrayBuffer(), {
    status: 200,
    headers: {
      "Cache-Control": "private, no-store",
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      "Content-Disposition": upstream.headers.get("content-disposition") ?? "attachment",
      "X-Artifact-SHA256": upstream.headers.get("x-artifact-sha256") ?? "",
      "X-Evidence-Manifest-SHA256": upstream.headers.get("x-evidence-manifest-sha256") ?? "",
    },
  });
}
