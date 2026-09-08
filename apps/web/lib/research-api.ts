import "server-only";
import { getBackendBearerAssertion } from "@/lib/backend-auth";

export class ResearchApiError extends Error {
  constructor(readonly status: number) { super("Research request unavailable"); }
}

export async function researchApi(path = "", init?: RequestInit) {
  const base = process.env.API_BASE_URL?.replace(/\/$/, "");
  if (!base) throw new ResearchApiError(503);
  const token = await getBackendBearerAssertion();
  const headers = new Headers({ Accept: "application/json" });
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else if (["localhost", "127.0.0.1"].includes(new URL(base).hostname)) {
    headers.set("X-Dev-User", process.env.API_DEV_USER || "portal-dev");
    headers.set("X-Dev-Roles", "viewer");
  } else throw new ResearchApiError(401);
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${base}/api/v1/research/runs${path}`, {
    ...init, headers, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new ResearchApiError(response.status);
  return response.json();
}

export async function wakeResearchWorker() {
  const base = process.env.RESEARCH_WORKER_URL?.replace(/\/$/, "");
  const secret = process.env.WORKER_TRIGGER_SECRET;
  if (!base || !secret) return; // A durable queue is also serviced by the recovery schedule.
  try {
    const response = await fetch(`${base}/internal/worker/research`, {
      method: "POST", headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
      body: "{}", cache: "no-store", redirect: "error", signal: AbortSignal.timeout(220_000),
    });
    if (!response.ok) console.error("Research worker trigger unavailable", response.status);
    await response.body?.cancel();
  } catch { console.error("Research worker trigger could not finish; checkpoint retained"); }
}

export function researchError(error: unknown) {
  return Response.json({ error: "research_unavailable" }, {
    status: error instanceof ResearchApiError ? error.status : 502,
    headers: { "Cache-Control": "private, no-store" },
  });
}

export function validMutation(request: Request) {
  const origin = request.headers.get("origin");
  return (!origin || origin === new URL(request.url).origin)
    && request.headers.get("sec-fetch-site") !== "cross-site"
    && request.headers.get("content-type")?.split(";")[0] === "application/json";
}

export const researchHeaders = { "Cache-Control": "private, no-store" };
export const researchId = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
