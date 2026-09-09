import { afterEach, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/backend-auth", () => ({ getBackendBearerAssertion: vi.fn().mockResolvedValue("signed-session") }));
import { backendOrigin } from "@/lib/backend-origin";
import { researchApi, wakeResearchWorker } from "@/lib/research-api";

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

it("preserves the existing service binding until an external backend is selected", () => {
  vi.stubEnv("API_BASE_URL", "https://existing.vercel.app/");
  vi.stubEnv("EXTERNAL_API_BASE_URL", "  ");
  expect(backendOrigin()).toBe("https://existing.vercel.app");
  vi.stubEnv("EXTERNAL_API_BASE_URL", " https://api.up.railway.app/// ");
  expect(backendOrigin()).toBe("https://api.up.railway.app");
});

it("forwards the existing signed browser identity to the selected backend", async () => {
  vi.stubEnv("API_BASE_URL", "https://existing.vercel.app");
  vi.stubEnv("EXTERNAL_API_BASE_URL", "https://api.up.railway.app");
  const fetcher = vi.fn().mockResolvedValue(Response.json({ items: [] }));
  vi.stubGlobal("fetch", fetcher);
  await researchApi();
  const [url, init] = fetcher.mock.calls[0];
  expect(url).toBe("https://api.up.railway.app/api/v1/research/runs");
  expect(init.headers.get("Authorization")).toBe("Bearer signed-session");
  expect(init.cache).toBe("no-store");
});

it("does not invoke the old HTTP worker when Railway consumes the durable queue", async () => {
  vi.stubEnv("RESEARCH_WORKER_MODE", "poll");
  vi.stubEnv("RESEARCH_WORKER_URL", "https://old-worker.vercel.app");
  vi.stubEnv("WORKER_TRIGGER_SECRET", "synthetic-fixture");
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  await wakeResearchWorker();
  expect(fetcher).not.toHaveBeenCalled();
});

it("retains HTTP wakeup by default for the current Vercel deployment", async () => {
  vi.stubEnv("RESEARCH_WORKER_MODE", "");
  vi.stubEnv("RESEARCH_WORKER_URL", "https://old-worker.vercel.app");
  vi.stubEnv("WORKER_TRIGGER_SECRET", "synthetic-fixture");
  const fetcher = vi.fn().mockResolvedValue(Response.json({ ok: true }));
  vi.stubGlobal("fetch", fetcher);
  await wakeResearchWorker();
  expect(fetcher).toHaveBeenCalledOnce();
  expect(fetcher.mock.calls[0][0]).toBe("https://old-worker.vercel.app/internal/worker/research");
});
