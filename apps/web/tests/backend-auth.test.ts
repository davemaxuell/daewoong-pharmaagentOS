import { afterEach, expect, it, vi } from "vitest";
import { exportPKCS8, generateKeyPair, jwtVerify } from "jose";
import { createVisitorSession } from "@/lib/visitor-session";

let token: string | undefined;
vi.mock("server-only", () => ({}));
vi.mock("react", () => ({ cache: (fn: unknown) => fn }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => token ? { value: token } : undefined }) }));
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("not-found"); } }));

afterEach(() => { vi.unstubAllEnvs(); token = undefined; });

it("issues only short-lived viewer assertions for an anonymous visitor", async () => {
  token = await createVisitorSession();
  const { privateKey, publicKey } = await generateKeyPair("RS256", { extractable: true });
  vi.stubEnv("API_SESSION_PRIVATE_KEY", await exportPKCS8(privateKey));
  vi.stubEnv("API_SESSION_ISSUER", "pharma-web");
  vi.stubEnv("API_SESSION_AUDIENCE", "pharma-api");
  const { getPortalIdentity, getBackendBearerAssertion, requirePortalRole } = await import("@/lib/backend-auth");
  const identity = await getPortalIdentity();
  expect(identity.roles).toEqual(["viewer"]);
  const { payload } = await jwtVerify(await getBackendBearerAssertion(), publicKey, {
    algorithms: ["RS256"], issuer: "pharma-web", audience: "pharma-api",
  });
  expect(payload.sub).toBe(identity.subject);
  expect(payload.token_use).toBe("public_session");
  expect(payload.roles).toEqual(["viewer"]);
  expect(payload.exp! - payload.iat!).toBe(90);
  await expect(requirePortalRole("admin")).rejects.toThrow("not-found");
  await expect(requirePortalRole("reviewer")).rejects.toThrow("not-found");
});

it("does not use a shared visitor identity when browser state is missing", async () => {
  const { getPortalIdentity } = await import("@/lib/backend-auth");
  await expect(getPortalIdentity()).rejects.toThrow("Browser session unavailable");
});
