import { queryRag, queryRagStream } from "@/lib/api-client";
import { getPortalIdentity } from "@/lib/backend-auth";
import type {
  ChatModelProfile,
  ChatRetrievalMode,
  RagConversationMessage,
  RagFilter,
  RagQueryOptions,
} from "@/lib/types";

export const runtime = "nodejs";
export const maxDuration = 120;

const MODEL_PROFILES = new Set<ChatModelProfile>(["auto", "fast", "balanced", "deep"]);
const RETRIEVAL_MODES = new Set<ChatRetrievalMode>([
  "auto",
  "none",
  "metadata",
  "letter",
  "corpus",
]);
const FILTER_KEYS = [
  "letterId",
  "company",
  "category",
  "regulation",
  "subtype",
  "issuingOffice",
  "dateFrom",
  "dateTo",
  "postedFrom",
  "postedTo",
] as const satisfies ReadonlyArray<keyof RagFilter>;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function boundedString(value: unknown, maximum = 2_000): string {
  return typeof value === "string" ? value.trim().slice(0, maximum) : "";
}

function normalizeFilters(value: unknown): RagFilter {
  const record = asRecord(value);
  return Object.fromEntries(
    FILTER_KEYS.flatMap((key) => {
      const normalized = boundedString(record[key], key === "letterId" ? 36 : 300);
      return normalized ? [[key, normalized]] : [];
    }),
  ) as RagFilter;
}

function normalizeHistory(value: unknown): RagConversationMessage[] {
  if (!Array.isArray(value)) return [];
  return value.slice(-8).flatMap((entry) => {
    const record = asRecord(entry);
    const role = record.role;
    const content = boundedString(record.content);
    return (role === "user" || role === "assistant") && content
      ? [{ role, content }]
      : [];
  });
}

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
        // A malformed proxy header is not an allowed origin.
      }
    }
    return allowedOrigins.has(originUrl.origin);
  } catch {
    return false;
  }
}

export async function POST(request: Request) {
  await getPortalIdentity();

  if (!hasSameRequestOrigin(request)) {
    return Response.json({ error: "Cross-origin chat requests are not allowed." }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return Response.json({ error: "A JSON request body is required." }, { status: 415 });
  }

  let body: Record<string, unknown>;
  try {
    body = asRecord(await request.json());
  } catch {
    return Response.json({ error: "The chat request body is invalid." }, { status: 400 });
  }

  const question = boundedString(body.question);
  if (question.length < 3) {
    return Response.json({ error: "Enter a question of at least 3 characters." }, { status: 422 });
  }
  const language = ["auto", "en", "ko"].includes(String(body.language))
    ? body.language as "auto" | "en" | "ko"
    : "auto";
  const rawMaximum = typeof body.maxSources === "number" ? body.maxSources : 6;
  const maxSources = Math.min(10, Math.max(1, Math.round(rawMaximum)));
  const rawOptions = asRecord(body.options);
  const threadId = boundedString(rawOptions.threadId, 36);
  const clientMessageId = boundedString(rawOptions.clientMessageId, 100);
  if (threadId && !UUID_PATTERN.test(threadId)) {
    return Response.json({ error: "The chat thread reference is invalid." }, { status: 422 });
  }
  const retrievalMode = RETRIEVAL_MODES.has(rawOptions.retrievalMode as ChatRetrievalMode)
    ? rawOptions.retrievalMode as ChatRetrievalMode
    : "auto";
  const modelProfile = MODEL_PROFILES.has(rawOptions.modelProfile as ChatModelProfile)
    ? rawOptions.modelProfile as ChatModelProfile
    : "auto";
  const options: RagQueryOptions = {
    threadId: threadId || undefined,
    clientMessageId: clientMessageId || undefined,
    retrievalMode,
    modelProfile,
  };
  const wantsNdjson = request.headers.get("accept")
    ?.toLowerCase()
    .split(",")
    .some((entry) => entry.trim().startsWith("application/x-ndjson")) ?? false;

  try {
    if (wantsNdjson) {
      const upstream = await queryRagStream(
        question,
        normalizeFilters(body.filters),
        language,
        maxSources,
        normalizeHistory(body.conversationHistory),
        options,
        request.signal,
      );
      if (!upstream.ok || !upstream.body) {
        console.error("Chat stream proxy failed", `Upstream status ${upstream.status}`);
        return Response.json(
          { error: "The verified chat stream could not be started." },
          { status: upstream.ok ? 502 : upstream.status },
        );
      }
      const upstreamType = upstream.headers.get("content-type")?.toLowerCase() ?? "";
      if (!upstreamType.includes("application/x-ndjson")) {
        await upstream.body.cancel();
        console.error("Chat stream proxy failed", "Upstream returned a non-NDJSON response");
        return Response.json(
          { error: "The verified chat stream returned an invalid format." },
          { status: 502 },
        );
      }
      return new Response(upstream.body, {
        status: upstream.status,
        headers: {
          "Cache-Control": "no-store, no-transform",
          "Content-Type": "application/x-ndjson; charset=utf-8",
          "Vary": "Accept",
          "X-Accel-Buffering": "no",
          "X-Content-Type-Options": "nosniff",
        },
      });
    }
    const result = await queryRag(
      question,
      normalizeFilters(body.filters),
      language,
      maxSources,
      normalizeHistory(body.conversationHistory),
      options,
      request.signal,
    );
    return Response.json(result, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    if (request.signal.aborted) {
      return new Response(null, { status: 499 });
    }
    console.error("Chat query proxy failed", error instanceof Error ? error.message : "Unknown error");
    return Response.json(
      { error: "The verified chat response could not be completed." },
      { status: 502 },
    );
  }
}
