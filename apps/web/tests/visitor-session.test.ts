import { afterEach, expect, it, vi } from "vitest";
import { SignJWT } from "jose";
import { createVisitorSession, readVisitorSession } from "@/lib/visitor-session";

afterEach(() => { vi.unstubAllEnvs(); });

it("rejects a browser cookie signed by a different deployment key", async () => {
  vi.stubEnv("PORTAL_SESSION_SECRET", "a".repeat(48));
  const token = await createVisitorSession();
  vi.stubEnv("PORTAL_SESSION_SECRET", "b".repeat(48));
  expect(await readVisitorSession(token)).toBeNull();
});

it("rejects expired browser state and provider-account subjects", async () => {
  for (const [subject, expires] of [
    [`anonymous:${crypto.randomUUID()}`, -1], ["google:former-account", 60],
  ] as const) {
    const token = await new SignJWT({})
      .setProtectedHeader({ alg: "HS256" }).setSubject(subject)
      .setIssuer("pharmaagent-os-browser").setAudience("pharmaagent-os-browser")
      .setIssuedAt().setExpirationTime(Math.floor(Date.now() / 1000) + expires)
      .sign(new Uint8Array(32));
    expect(await readVisitorSession(token)).toBeNull();
  }
});

it("requires a configured signing secret in production", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("PORTAL_SESSION_SECRET", "");
  await expect(createVisitorSession()).rejects.toThrow("PORTAL_SESSION_SECRET");
});
