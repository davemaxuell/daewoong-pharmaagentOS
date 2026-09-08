import { beforeEach, expect, it, vi } from "vitest";
import { GET } from "@/app/api/portal/sidebar/route";

const mocks = vi.hoisted(() => ({ auth: vi.fn(), history: vi.fn(), changes: vi.fn() }));
vi.mock("@/lib/backend-auth", () => ({ requirePortalRole: mocks.auth }));
vi.mock("@/lib/api-client", () => ({ getChatThreads: mocks.history, getNewLetterChanges: mocks.changes }));

beforeEach(() => {
  vi.resetAllMocks();
  mocks.auth.mockResolvedValue({ subject: "isolated-session", roles: ["viewer"] });
  mocks.history.mockResolvedValue({ mode: "live", data: { items: [] } });
  mocks.changes.mockResolvedValue({ data: [{ id: "latest", occurredAt: "2026-09-08" }] });
});

it("loads private sidebar data separately and requests only the newest notification", async () => {
  const response = await GET();
  expect(mocks.auth).toHaveBeenCalledWith("viewer");
  expect(mocks.changes).toHaveBeenCalledWith(1);
  expect(response.headers.get("cache-control")).toBe("private, no-store");
  expect(await response.json()).toEqual({ threads: [], historyLoadState: "ready", notification: { latestEventId: "latest", occurredAt: "2026-09-08" } });
});

it("does not read sidebar data before authorization succeeds", async () => {
  mocks.auth.mockRejectedValue(new Error("unauthorized"));
  await expect(GET()).rejects.toThrow("unauthorized");
  expect(mocks.history).not.toHaveBeenCalled();
  expect(mocks.changes).not.toHaveBeenCalled();
});

it("keeps history usable when the notification service fails", async () => {
  mocks.changes.mockRejectedValue(new Error("unavailable"));
  expect((await (await GET()).json()).historyLoadState).toBe("ready");
});
