import type { GoogleProfile } from "next-auth/providers/google";
import type { NaverProfile } from "next-auth/providers/naver";
import { APP_ROLES, type AppRole, type AuthProvider } from "@/lib/auth-types";

export function normalizeEmail(value: unknown) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

function providerSubject(provider: AuthProvider, value: unknown) {
  if (typeof value !== "string") return null;
  const subject = value.trim();
  if (!subject || subject.length > 255 || subject.includes(":")) return null;
  return `${provider}:${subject}`;
}

export function googleSubject(value: unknown) {
  return providerSubject("google", value);
}

export function naverSubject(value: unknown) {
  return providerSubject("naver", value);
}

export function isGoogleSubject(value: unknown): value is string {
  return typeof value === "string" && /^google:[^:]{1,255}$/.test(value);
}

export function isNaverSubject(value: unknown): value is string {
  return typeof value === "string" && /^naver:[^:]{1,255}$/.test(value);
}

export function isTrustedAuthSubject(value: unknown): value is string {
  return isGoogleSubject(value) || isNaverSubject(value);
}

export function providerForSubject(value: unknown): AuthProvider | null {
  if (isGoogleSubject(value)) return "google";
  if (isNaverSubject(value)) return "naver";
  return null;
}

/** All portal access requires an authenticated Google or Naver identity. */
export function isAuthRequired() {
  return true;
}

export function rolesForEmail(value: unknown): AppRole[] {
  void value;
  return ["viewer"];
}

/**
 * Resolve server-assigned roles from immutable provider subjects, never email.
 *
 * The optional argument keeps parsing deterministic and directly testable. Server
 * callers omit it and read the deployment's private JSON role directory.
 */
export function rolesForSubject(
  value: unknown,
  serializedDirectory = process.env.AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON,
): AppRole[] {
  if (!isTrustedAuthSubject(value)) return [];
  if (!serializedDirectory?.trim()) return ["viewer"];

  let parsed: unknown;
  try {
    parsed = JSON.parse(serializedDirectory);
  } catch {
    throw new Error("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON must be valid JSON.");
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON must be a JSON object.");
  }

  const entries = Object.entries(parsed);
  if (entries.length > 500) {
    throw new Error("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON exceeds 500 subjects.");
  }
  const allowedRoles = new Set<string>(APP_ROLES);
  let assigned: AppRole[] | undefined;
  for (const [subject, rawRoles] of entries) {
    if (!isTrustedAuthSubject(subject)) {
      throw new Error("Every role assignment key must be an immutable Google or Naver subject.");
    }
    if (!Array.isArray(rawRoles) || rawRoles.length === 0 || rawRoles.length > APP_ROLES.length) {
      throw new Error(`Role assignment for ${subject} must be a non-empty role array.`);
    }
    const roles = rawRoles.map((role) => {
      if (typeof role !== "string" || !allowedRoles.has(role)) {
        throw new Error(`Role assignment for ${subject} contains an unknown role.`);
      }
      return role as AppRole;
    });
    if (new Set(roles).size !== roles.length) {
      throw new Error(`Role assignment for ${subject} contains duplicate roles.`);
    }
    if (subject === value) assigned = roles;
  }

  if (!assigned) return ["viewer"];
  const assignedSet = new Set(assigned);
  return APP_ROLES.filter((role) => assignedSet.has(role));
}

export function isAllowedEmail(value: unknown) {
  return Boolean(normalizeEmail(value));
}

export function isAllowedGoogleProfile(profile: GoogleProfile) {
  const email = normalizeEmail(profile.email);
  const subject = googleSubject(profile.sub);
  if (profile.email_verified !== true || !subject || !email || !isAllowedEmail(email)) {
    return false;
  }
  return true;
}

export function isAllowedNaverProfile(profile: NaverProfile) {
  const response = profile.response;
  const email = normalizeEmail(response?.email);
  const subject = naverSubject(response?.id);

  // A stable Naver provider ID and consented email establish the account. The
  // email may use any domain; authentication is tied to Naver's immutable ID.
  return (
    profile.resultcode === "00" &&
    subject !== null &&
    Boolean(email) &&
    isAllowedEmail(email)
  );
}
