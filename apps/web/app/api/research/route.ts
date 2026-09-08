import { after } from "next/server";
import { getPortalIdentity } from "@/lib/backend-auth";
import { researchApi, researchError, researchHeaders, researchId, validMutation, wakeResearchWorker } from "@/lib/research-api";

export const maxDuration = 300;

export async function GET() {
  try {
    await getPortalIdentity();
    return Response.json(await researchApi(), { headers: researchHeaders });
  } catch (error) { return researchError(error); }
}

export async function POST(request: Request) {
  if (!validMutation(request)) return new Response(null, { status: 403 });
  try {
    await getPortalIdentity();
    const body = await request.text();
    if (body.length > 8_000) return new Response(null, { status: 413 });
    let input;
    try { input = JSON.parse(body); } catch { return new Response(null, { status: 422 }); }
    if (!input || typeof input.objective !== "string" || input.objective.trim().length < 8
      || input.objective.length > 2_000 || !["en", "ko"].includes(input.language)
      || typeof input.client_request_id !== "string" || !researchId.test(input.client_request_id)) {
      return new Response(null, { status: 422 });
    }
    const run = await researchApi("", { method: "POST", body: JSON.stringify({
      objective: input.objective, language: input.language, client_request_id: input.client_request_id,
    }) });
    after(wakeResearchWorker);
    return Response.json(run, { status: 201, headers: researchHeaders });
  } catch (error) { return researchError(error); }
}
