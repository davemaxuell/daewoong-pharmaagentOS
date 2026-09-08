import { beforeEach, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
const mocks = vi.hoisted(() => ({ identity: vi.fn(), api: vi.fn(), wake: vi.fn(), after: vi.fn() }));
vi.mock("@/lib/backend-auth", () => ({ getPortalIdentity: mocks.identity }));
vi.mock("next/server", () => ({ after: mocks.after }));
vi.mock("@/lib/research-api", async (original) => ({
  ...await original<typeof import("@/lib/research-api")>(), researchApi: mocks.api, wakeResearchWorker: mocks.wake,
}));
import { POST } from "@/app/api/research/route";
import { POST as control } from "@/app/api/research/[id]/route";

const id = "11111111-1111-4111-8111-111111111111";
beforeEach(() => { vi.resetAllMocks(); mocks.identity.mockResolvedValue({ subject: "test" }); mocks.api.mockResolvedValue({ id }); });
const request = (data: unknown, origin = "https://portal.example") => new Request("https://portal.example/api/research", {
  method: "POST", headers: { "Content-Type": "application/json", origin }, body: JSON.stringify(data),
});

it("saves the task before scheduling background work and strips caller execution fields", async () => {
  const response = await POST(request({ objective: "Prepare a review brief", language: "en", client_request_id: id, owner_id: "someone-else", tools: ["send_email"] }));
  expect(response.status).toBe(201);
  expect(response.headers.get("cache-control")).toBe("private, no-store");
  const body = JSON.parse(mocks.api.mock.calls[0][1].body);
  expect(body.owner_id).toBeUndefined(); expect(body.tools).toBeUndefined();
  expect(mocks.after).toHaveBeenCalledWith(mocks.wake);
  expect(mocks.wake).not.toHaveBeenCalled();
});

it("rejects cross-origin writes before invoking the agent", async () => {
  expect((await POST(request({}, "https://another.example"))).status).toBe(403);
  expect(mocks.api).not.toHaveBeenCalled(); expect(mocks.after).not.toHaveBeenCalled();
});

it("does not queue work if saving or authorization fails", async () => {
  mocks.identity.mockRejectedValue(new Error("no session"));
  expect((await POST(request({ objective: "Prepare a review brief", language: "en", client_request_id: id }))).status).toBe(502);
  expect(mocks.api).not.toHaveBeenCalled(); expect(mocks.after).not.toHaveBeenCalled();
});

it("Stop never triggers more background work", async () => {
  const response = await control(request({ action: "stop" }), { params: Promise.resolve({ id }) });
  expect(response.status).toBe(200);
  expect(mocks.api).toHaveBeenCalledWith(`/${id}/stop`, { method: "POST" });
  expect(mocks.after).not.toHaveBeenCalled();
});
