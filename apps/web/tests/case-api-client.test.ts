import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/backend-auth", () => ({
  getBackendBearerAssertion: vi.fn(async () => "test-assertion"),
}));

const CASE_ID = "11111111-1111-4111-8111-111111111111";
const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);

function event(sequence: number) {
  return {
    id: `${sequence.toString().padStart(8, "0")}-9999-4999-8999-999999999999`,
    case_id: CASE_ID,
    sequence,
    event_type: "CASE_UPDATED",
    actor_type: "user",
    actor_id: "google:analyst-123",
    request_id: `request-${sequence}`,
    payload: { sequence },
    previous_event_hash: sequence === 1 ? null : HASH_A,
    event_hash: HASH_B,
    state_hash: HASH_A,
    occurred_at: "2026-09-04T08:04:00Z",
  };
}

function eventPage(
  items: ReturnType<typeof event>[],
  nextCursor: string | null,
  hasMore: boolean,
) {
  return new Response(JSON.stringify({
    items,
    next_cursor: nextCursor,
    has_more: hasMore,
  }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("API_BASE_URL", "https://case-api.example");
  fetchMock = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("complete case-event history pagination", () => {
  it("fetches every page and aggregates events in service order", async () => {
    fetchMock
      .mockResolvedValueOnce(eventPage([event(1), event(2)], "page two", true))
      .mockResolvedValueOnce(eventPage([event(3)], null, false));
    const { getAgentCaseEvents } = await import("@/lib/case-api-client");

    const history = await getAgentCaseEvents(CASE_ID);

    expect(history.items.map(({ sequence }) => sequence)).toEqual([1, 2, 3]);
    expect(history).toMatchObject({ nextCursor: null, hasMore: false });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `https://case-api.example/api/v1/cases/${CASE_ID}/events?limit=200`,
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      `https://case-api.example/api/v1/cases/${CASE_ID}/events?limit=200&cursor=page+two`,
    );
  });

  it("fails explicitly when the service repeats a continuation cursor", async () => {
    fetchMock
      .mockResolvedValueOnce(eventPage([event(1)], "repeat-me", true))
      .mockResolvedValueOnce(eventPage([event(2)], "repeat-me", true));
    const { getAgentCaseEvents } = await import("@/lib/case-api-client");

    await expect(getAgentCaseEvents(CASE_ID)).rejects.toThrow(/repeated an event-history cursor/i);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("fails explicitly instead of returning a partial history at the safety bound", async () => {
    const { CASE_EVENT_MAX_PAGES, CASE_EVENT_PAGE_LIMIT, getAgentCaseEvents } = await import(
      "@/lib/case-api-client"
    );
    fetchMock.mockImplementation(async () => {
      const sequence = fetchMock.mock.calls.length;
      return eventPage([event(sequence)], `cursor-${sequence}`, true);
    });

    await expect(getAgentCaseEvents(CASE_ID)).rejects.toThrow(
      new RegExp(
        `${CASE_EVENT_MAX_PAGES}-page safety limit.*${CASE_EVENT_MAX_PAGES * CASE_EVENT_PAGE_LIMIT} events`,
        "i",
      ),
    );
    expect(fetchMock).toHaveBeenCalledTimes(CASE_EVENT_MAX_PAGES);
  });
});
