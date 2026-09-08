import { after } from "next/server";
import { getPortalIdentity } from "@/lib/backend-auth";
import { researchApi, researchError, researchHeaders, researchId, validMutation, wakeResearchWorker } from "@/lib/research-api";

export const maxDuration = 300;
type Context = { params: Promise<{ id: string }> };

export async function GET(request: Request, context: Context) {
  try {
    await getPortalIdentity();
    const { id } = await context.params;
    if (!researchId.test(id)) return new Response(null, { status: 404 });
    const afterSequence = new URL(request.url).searchParams.get("after") || "0";
    if (!/^\d{1,5}$/.test(afterSequence) || Number(afterSequence) > 10_000) return new Response(null, { status: 422 });
    return Response.json(await researchApi(`/${id}?after=${afterSequence}`), { headers: researchHeaders });
  } catch (error) { return researchError(error); }
}

export async function POST(request: Request, context: Context) {
  if (!validMutation(request)) return new Response(null, { status: 403 });
  try {
    await getPortalIdentity();
    const { id } = await context.params;
    if (!researchId.test(id)) return new Response(null, { status: 404 });
    const body = await request.text();
    if (body.length > 100) return new Response(null, { status: 413 });
    let input;
    try { input = JSON.parse(body); } catch { return new Response(null, { status: 422 }); }
    if (!input || !["stop", "resume"].includes(input.action)) return new Response(null, { status: 422 });
    const result = await researchApi(`/${id}/${input.action}`, { method: "POST" });
    if (input.action === "resume") after(wakeResearchWorker);
    return Response.json(result, { headers: researchHeaders });
  } catch (error) { return researchError(error); }
}
