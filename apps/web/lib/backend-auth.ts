import "server-only";

import { randomUUID } from "node:crypto";
import { importPKCS8, SignJWT } from "jose";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { cache } from "react";
import { isVisitorSubject, readVisitorSession, visitorCookieName } from "@/lib/visitor-session";
import type { AppRole, PortalIdentity } from "@/lib/auth-types";

let cachedPrivateKeyPem: string | undefined;
let cachedPrivateKey: ReturnType<typeof importPKCS8> | undefined;

function normalizePem(value: string) {
  return value.replace(/\\n/g, "\n").trim();
}

function requiredEnvironment(name: string) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required for the backend connection.`);
  return value;
}

function signingKey() {
  const pem = normalizePem(requiredEnvironment("API_SESSION_PRIVATE_KEY"));
  if (!pem.includes("BEGIN PRIVATE KEY")) {
    throw new Error("API_SESSION_PRIVATE_KEY must be a PKCS#8 PEM private key.");
  }

  if (!cachedPrivateKey || cachedPrivateKeyPem !== pem) {
    cachedPrivateKeyPem = pem;
    cachedPrivateKey = importPKCS8(pem, "RS256");
  }
  return cachedPrivateKey;
}

export const getPortalIdentity = cache(async (): Promise<PortalIdentity> => {
  const cookieStore = await cookies();
  const subject = await readVisitorSession(cookieStore.get(visitorCookieName())?.value);
  if (!subject) throw new Error("Browser session unavailable. Refresh the page and try again.");
  return { subject, roles: ["viewer"] };
});

/**
 * Enforces authorization at the server entry point. Pages and Server Actions
 * must call this independently; hiding a navigation item is not a security
 * boundary.
 */
export async function requirePortalRole(
  requiredRole: AppRole | readonly AppRole[],
): Promise<PortalIdentity> {
  const identity = await getPortalIdentity();
  const allowedRoles = Array.isArray(requiredRole) ? requiredRole : [requiredRole];
  if (!allowedRoles.some((role) => identity.roles.includes(role))) {
    notFound();
  }
  return identity;
}

/**
 * Creates a server-to-server assertion for the FastAPI origin.
 * Anonymous browser sessions receive only viewer authority. The assertion and
 * signing key never leave the web server.
 */
export async function getBackendBearerAssertion(): Promise<string> {
  const identity = await getPortalIdentity();
  if (!isVisitorSubject(identity.subject)) {
    throw new Error("The browser session is invalid.");
  }

  const issuer = requiredEnvironment("API_SESSION_ISSUER");
  const audience = requiredEnvironment("API_SESSION_AUDIENCE");
  const keyId = process.env.API_SESSION_KEY_ID?.trim();
  const now = Math.floor(Date.now() / 1000);
  const roles = identity.roles;

  return new SignJWT({ roles, token_use: "public_session" })
    .setProtectedHeader({ alg: "RS256", typ: "JWT", ...(keyId ? { kid: keyId } : {}) })
    .setSubject(identity.subject)
    .setIssuer(issuer)
    .setAudience(audience)
    .setJti(randomUUID())
    .setIssuedAt(now)
    .setNotBefore(now - 5)
    .setExpirationTime(now + 90)
    .sign(await signingKey());
}
