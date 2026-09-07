import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { NextRequest, type NextFetchEvent } from "next/server";
import { encode } from "next-auth/jwt";

let portalProxy: typeof import("@/proxy").proxy;

beforeAll(async () => {
  vi.stubEnv("AUTH_SECRET", "test-only-auth-secret-with-more-than-32-characters");
  vi.stubEnv("AUTH_URL", "http://localhost:3000");
  vi.stubEnv("AUTH_GOOGLE_ID", "test-google-id");
  vi.stubEnv("AUTH_GOOGLE_SECRET", "test-google-secret");
  vi.stubEnv("AUTH_NAVER_ID", "test-naver-id");
  vi.stubEnv("AUTH_NAVER_SECRET", "test-naver-secret");
  ({ proxy: portalProxy } = await import("@/proxy"));
});

afterAll(() => {
  vi.unstubAllEnvs();
});

function fetchEvent() {
  return {
    waitUntil: vi.fn(),
    passThroughOnException: vi.fn(),
  } as unknown as NextFetchEvent;
}

describe("signed-out route boundary", () => {
  it("rejects a still-valid session cookie when restricted admission is revoked", async () => {
    vi.stubEnv("AUTH_ADMISSION_MODE", "restricted");
    vi.stubEnv("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON", '{"google:removed-user":["viewer"]}');
    try {
      const cookieName = "authjs.session-token";
      const token = await encode({
        secret: process.env.AUTH_SECRET!,
        salt: cookieName,
        token: { sub: "google:removed-user", email: "viewer@example.com", roles: ["viewer"] },
      });
      const admitted = await portalProxy(new NextRequest("http://localhost:3000/api/chat/query", {
        method: "POST", headers: { cookie: `${cookieName}=${token}` },
      }), fetchEvent());
      expect(admitted?.status).toBe(200);
      vi.stubEnv("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON", "{}");
      const response = await portalProxy(new NextRequest("http://localhost:3000/api/chat/query", {
        method: "POST", headers: { cookie: `${cookieName}=${token}` },
      }), fetchEvent());
      expect(response?.status).toBe(401);
    } finally {
      vi.stubEnv("AUTH_ADMISSION_MODE", "public");
    }
  });
  it("redirects a protected page and preserves its relative destination", async () => {
    const request = new NextRequest(
      "http://localhost:3000/drug-letters?category=Laboratory",
    );
    const response = await portalProxy(request, fetchEvent());
    if (!response) throw new Error("The proxy did not return a redirect response.");

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/sign-in?callbackUrl=%2Fdrug-letters%3Fcategory%3DLaboratory",
    );
  });

  it("returns JSON 401 for a protected application API", async () => {
    const request = new NextRequest("http://localhost:3000/api/chat/query", {
      method: "POST",
    });
    const response = await portalProxy(request, fetchEvent());
    if (!response) throw new Error("The proxy did not return an API response.");

    expect(response.status).toBe(401);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expect(response.json()).resolves.toEqual({
      error: "Authentication with Google or Naver is required.",
    });
  });
});
