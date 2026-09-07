import { afterEach, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("react", () => ({ cache: (fn: unknown) => fn }));
vi.mock("next/navigation", () => ({
  redirect: () => { throw new Error("redirect-to-sign-in"); },
  notFound: () => { throw new Error("not-found"); },
}));
vi.mock("@/auth", async () => ({
  ...await import("@/lib/auth-policy"),
  auth: async () => ({ user: { subject: "google:123", email: "viewer@example.com" } }),
}));

afterEach(() => { vi.unstubAllEnvs(); });

it("rejects an existing session and refuses an API assertion after admission is revoked", async () => {
  vi.stubEnv("AUTH_ADMISSION_MODE", "restricted");
  vi.stubEnv("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON", '{"google:123":["viewer"]}');
  const { getAuthenticatedPortalIdentity, getBackendBearerAssertion } = await import("@/lib/backend-auth");
  expect(await getAuthenticatedPortalIdentity()).toMatchObject({ roles: ["viewer"] });
  vi.stubEnv("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON", "{}");
  expect(await getAuthenticatedPortalIdentity()).toBeNull();
  await expect(getBackendBearerAssertion()).rejects.toThrow("redirect-to-sign-in");
});
