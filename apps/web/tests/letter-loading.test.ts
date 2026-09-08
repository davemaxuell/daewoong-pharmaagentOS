import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/backend-auth", () => ({
  getBackendBearerAssertion: vi.fn(async () => "test-assertion"),
}));

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("API_BASE_URL", "https://letter-api.example");
  fetchMock = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

it("loads 440 catalog entries with one authorized request", async () => {
  const items = Array.from({ length: 440 }, (_, index) => ({ id: String(index), company_name: `Company ${index}` }));
  fetchMock.mockResolvedValueOnce(Response.json({ items, has_more: false }));
  const { getLetters } = await import("@/lib/api-client");
  expect((await getLetters()).data).toHaveLength(440);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe("https://letter-api.example/api/v1/letters/catalog?limit=1000");
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer test-assertion");
  expect(options?.cache).toBe("no-store");
});

it("continues catalog pagination and rejects a repeated cursor", async () => {
  fetchMock
    .mockResolvedValueOnce(Response.json({ items: [{ id: "first", company_name: "First" }], has_more: true, next_cursor: "next" }))
    .mockResolvedValueOnce(Response.json({ items: [{ id: "second", company_name: "Second" }], has_more: true, next_cursor: "next" }));
  const { getLetters } = await import("@/lib/api-client");
  await expect(getLetters()).rejects.toThrow("pagination did not advance");
  expect(fetchMock.mock.calls[1][0]).toBe("https://letter-api.example/api/v1/letters/catalog?limit=1000&cursor=next");
});

it("keeps the displayed document's version and hash without fetching other document histories", async () => {
  fetchMock.mockResolvedValueOnce(Response.json({
    id: "letter", company_name: "Company", normalized_markdown: "Official source text",
    current_version: { id: "current", version_number: 3, canonical_hash: "a".repeat(64) },
  }));
  const { getLetter } = await import("@/lib/api-client");
  const { data } = await getLetter("letter");
  expect(data?.sourceVersion).toBe("v3");
  expect(data?.sourceHash).toBe("a".repeat(64));
  expect(data?.originalSections.length).toBeGreaterThan(0);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toBe("https://letter-api.example/api/v1/letters/letter");
});
