import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";
import { readVisitorSession, visitorCookieName } from "@/lib/visitor-session";

afterEach(() => vi.unstubAllEnvs());

describe("account-free browsing", () => {
  it("opens the dashboard and forwards a browser session on the first request", async () => {
    const response = await proxy(new NextRequest("http://localhost:3000/dashboard"));
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    const cookie = response.cookies.get(visitorCookieName());
    expect(cookie?.httpOnly).toBe(true);
    expect(cookie?.sameSite).toBe("lax");
    expect(await readVisitorSession(cookie?.value)).toMatch(/^anonymous:/);
    expect(response.headers.get("x-middleware-request-cookie")).toContain(cookie!.value);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
  });

  it("gives separate visitors distinct identities and retains a returning visitor", async () => {
    const first = await proxy(new NextRequest("http://localhost:3000/dashboard"));
    const second = await proxy(new NextRequest("http://localhost:3000/dashboard"));
    const name = visitorCookieName();
    expect(first.cookies.get(name)?.value).not.toBe(second.cookies.get(name)?.value);
    const token = first.cookies.get(name)!.value;
    const returning = await proxy(new NextRequest("http://localhost:3000/api/chat/query", {
      method: "POST", headers: { cookie: `${name}=${token}` },
    }));
    expect(returning.status).toBe(200);
    expect(returning.headers.get("set-cookie")).toBeNull();
    expect(returning.headers.get("x-middleware-request-cookie")).toContain(token);
  });

  it("replaces a forged cookie instead of accepting its identity", async () => {
    const response = await proxy(new NextRequest("http://localhost:3000/dashboard", {
      headers: { cookie: `${visitorCookieName()}=forged-admin-cookie` },
    }));
    expect(await readVisitorSession(response.cookies.get(visitorCookieName())?.value))
      .toMatch(/^anonymous:/);
  });

  it("uses a secure host-only cookie on a hosted deployment", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("PORTAL_SESSION_SECRET", "x".repeat(48));
    const response = await proxy(new NextRequest("https://pharma.example/dashboard"));
    const cookie = response.cookies.get("__Host-pharma-visitor");
    expect(cookie?.secure).toBe(true);
    expect(cookie?.path).toBe("/");
    expect(cookie?.domain).toBeUndefined();
  });
});
