import { jwtVerify, SignJWT } from "jose";

export const VISITOR_SESSION_SECONDS = 30 * 24 * 60 * 60;
const SESSION_AUDIENCE = "pharmaagent-os-browser";

export function visitorCookieName() {
  return process.env.NODE_ENV === "production" ? "__Host-pharma-visitor" : "pharma-visitor";
}

function sessionKey() {
  const value = process.env.PORTAL_SESSION_SECRET;
  if (value && value.length >= 32) return new TextEncoder().encode(value);
  if (process.env.NODE_ENV === "production" || process.env.VERCEL === "1") {
    throw new Error("PORTAL_SESSION_SECRET must contain at least 32 characters.");
  }
  // Local-only browser isolation; hosted requests always require a configured key.
  return new Uint8Array(32);
}

export function isVisitorSubject(value: unknown): value is string {
  return typeof value === "string" &&
    /^anonymous:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);
}

export async function readVisitorSession(token: string | undefined): Promise<string | null> {
  const key = sessionKey();
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, key, {
      algorithms: ["HS256"], issuer: SESSION_AUDIENCE, audience: SESSION_AUDIENCE,
      requiredClaims: ["sub", "iat", "exp"], maxTokenAge: VISITOR_SESSION_SECONDS,
    });
    return isVisitorSubject(payload.sub) ? payload.sub : null;
  } catch {
    return null;
  }
}

export async function createVisitorSession() {
  return new SignJWT({})
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setSubject(`anonymous:${crypto.randomUUID()}`)
    .setIssuer(SESSION_AUDIENCE)
    .setAudience(SESSION_AUDIENCE)
    .setIssuedAt()
    .setExpirationTime(`${VISITOR_SESSION_SECONDS}s`)
    .sign(sessionKey());
}
