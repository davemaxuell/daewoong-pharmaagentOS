import "server-only";

import { randomUUID } from "node:crypto";
import { importPKCS8, SignJWT } from "jose";
import { notFound, redirect } from "next/navigation";
import { cache } from "react";
import {
  auth,
  isAllowedEmail,
  providerForSubject,
  isTrustedAuthSubject,
  rolesForSubject,
} from "@/auth";
import type { AppRole, PortalIdentity } from "@/lib/auth-types";

let cachedPrivateKeyPem: string | undefined;
let cachedPrivateKey: ReturnType<typeof importPKCS8> | undefined;

function normalizePem(value: string) {
  return value.replace(/\\n/g, "\n").trim();
}

function requiredEnvironment(name: string) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required when authentication is enabled.`);
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

export const getAuthenticatedPortalIdentity = cache(async (): Promise<PortalIdentity | null> => {
  const session = await auth();
  const provider = providerForSubject(session?.user?.subject);
  if (
    session?.user &&
    provider &&
    isTrustedAuthSubject(session.user.subject) &&
    isAllowedEmail(session.user.email)
  ) {
    return {
      subject: session.user.subject,
      name: session.user.name ?? null,
      email: session.user.email ?? null,
      image: session.user.image ?? null,
      provider,
      roles: rolesForSubject(session.user.subject),
      authenticated: true,
    };
  }

  return null;
});

export const getPortalIdentity = cache(async (): Promise<PortalIdentity> => {
  const identity = await getAuthenticatedPortalIdentity();
  if (identity) return identity;

  redirect("/sign-in?callbackUrl=%2Fdashboard");
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
 * Provider OAuth tokens never leave Auth.js and this function must never be imported by a Client Component.
 */
export async function getBackendBearerAssertion(): Promise<string> {
  const identity = await getPortalIdentity();
  if (!isTrustedAuthSubject(identity.subject)) {
    throw new Error("The authenticated session does not contain a trusted provider subject.");
  }

  const issuer = requiredEnvironment("API_SESSION_ISSUER");
  const audience = requiredEnvironment("API_SESSION_AUDIENCE");
  const keyId = process.env.API_SESSION_KEY_ID?.trim();
  const now = Math.floor(Date.now() / 1000);
  const roles = identity.roles;

  return new SignJWT({ roles, token_use: "api_session" })
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
