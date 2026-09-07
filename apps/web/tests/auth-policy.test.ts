import { afterEach, describe, expect, it, vi } from "vitest";
import type { GoogleProfile } from "next-auth/providers/google";
import type { NaverProfile } from "next-auth/providers/naver";
import {
  googleSubject,
  isAllowedEmail,
  isAllowedGoogleProfile,
  isAllowedNaverProfile,
  isAuthRequired,
  isTrustedAuthSubject,
  naverSubject,
  providerForSubject,
  rolesForEmail,
  rolesForSubject,
} from "@/lib/auth-policy";
import { safeAuthCallbackUrl } from "@/lib/auth-redirect";

function googleProfile(overrides: Partial<GoogleProfile> = {}) {
  return {
    sub: "google-user-123",
    email: "viewer@example.com",
    email_verified: true,
    name: "Portal Viewer",
    ...overrides,
  } as GoogleProfile;
}

function naverProfile(overrides: Record<string, unknown> = {}) {
  return {
    resultcode: "00",
    message: "success",
    response: {
      id: "naver-user-123",
      email: "viewer@example.org",
      name: "Portal Viewer",
      ...overrides,
    },
  } as unknown as NaverProfile;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("mandatory portal authentication", () => {
  it("cannot be disabled through the former development flag", () => {
    vi.stubEnv("AUTH_REQUIRED", "false");
    expect(isAuthRequired()).toBe(true);
  });

  it("uses provider-scoped immutable account subjects", () => {
    expect(googleSubject("123")).toBe("google:123");
    expect(naverSubject("123")).toBe("naver:123");
    expect(googleSubject("bad:subject")).toBeNull();
    expect(isTrustedAuthSubject("google:123")).toBe(true);
    expect(isTrustedAuthSubject("naver:123")).toBe(true);
    expect(isTrustedAuthSubject("dev:123")).toBe(false);
    expect(providerForSubject("google:123")).toBe("google");
    expect(providerForSubject("naver:123")).toBe("naver");
  });
});

describe("normal viewer admission", () => {
  it("accepts any verified Google or valid Naver profile with an email", () => {
    expect(isAllowedGoogleProfile(googleProfile())).toBe(true);
    expect(isAllowedGoogleProfile(googleProfile({ email_verified: false }))).toBe(false);
    expect(isAllowedGoogleProfile(googleProfile({ sub: "" }))).toBe(false);
    expect(isAllowedGoogleProfile(googleProfile({ email: "" }))).toBe(false);
    expect(isAllowedGoogleProfile(googleProfile({ email: "anyone@example.com" }))).toBe(true);
    expect(isAllowedNaverProfile(naverProfile())).toBe(true);
    expect(isAllowedNaverProfile(naverProfile({ id: "" }))).toBe(false);
    expect(isAllowedNaverProfile(naverProfile({ email: "" }))).toBe(false);
    expect(isAllowedNaverProfile(naverProfile({ email: "anyone@example.org" }))).toBe(true);
  });

  it("requires a non-empty email", () => {
    expect(isAllowedEmail("anyone@example.com")).toBe(true);
    expect(isAllowedEmail(" ")).toBe(false);
    expect(isAllowedEmail(undefined)).toBe(false);
  });
});

describe("single viewer role", () => {
  it("never grants reviewer or admin privileges from email configuration", () => {
    vi.stubEnv("AUTH_REVIEWER_EMAILS", "reviewer@example.com");
    vi.stubEnv("AUTH_ADMIN_EMAILS", "admin@example.com");

    expect(rolesForEmail("viewer@example.com")).toEqual(["viewer"]);
    expect(rolesForEmail("reviewer@example.com")).toEqual(["viewer"]);
    expect(rolesForEmail("admin@example.com")).toEqual(["viewer"]);
  });

  it("assigns privileged roles only from an immutable-subject server directory", () => {
    const directory = JSON.stringify({
      "google:analyst-123": ["system_owner", "analyst"],
      "naver:reviewer-456": ["reviewer"],
    });

    expect(rolesForSubject("google:unassigned", directory)).toEqual(["viewer"]);
    expect(rolesForSubject("google:analyst-123", directory)).toEqual([
      "analyst",
      "system_owner",
    ]);
    expect(rolesForSubject("naver:reviewer-456", directory)).toEqual(["reviewer"]);
    expect(rolesForSubject("email:analyst@example.com", directory)).toEqual([]);
  });

  it("fails closed for malformed or ambiguous role directories", () => {
    expect(() => rolesForSubject("google:123", "not-json")).toThrow(/valid JSON/);
    expect(() => rolesForSubject("google:123", JSON.stringify({
      "analyst@example.com": ["analyst"],
    }))).toThrow(/immutable Google or Naver subject/);
    expect(() => rolesForSubject("google:123", JSON.stringify({
      "google:123": ["superuser"],
    }))).toThrow(/unknown role/);
    expect(() => rolesForSubject("google:123", JSON.stringify({
      "google:123": ["analyst", "analyst"],
    }))).toThrow(/duplicate roles/);
  });
});

describe("restricted portal admission", () => {
  it("denies unassigned accounts from both providers", () => {
    vi.stubEnv("AUTH_ADMISSION_MODE", "restricted");
    vi.stubEnv("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON", "{}");
    expect(isAllowedGoogleProfile(googleProfile())).toBe(false);
    expect(isAllowedNaverProfile(naverProfile())).toBe(false);
    expect(rolesForSubject("google:unassigned")).toEqual([]);
  });

  it("admits only exact provider subjects, independently of email", () => {
    vi.stubEnv("AUTH_ADMISSION_MODE", "restricted");
    vi.stubEnv("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON", JSON.stringify({
      "google:google-user-123": ["viewer"],
      "naver:naver-user-123": ["reviewer"],
    }));
    expect(isAllowedGoogleProfile(googleProfile())).toBe(true);
    expect(isAllowedNaverProfile(naverProfile())).toBe(true);
    expect(isAllowedGoogleProfile(googleProfile({ sub: "different-account" }))).toBe(false);
    expect(isAllowedNaverProfile(naverProfile({ id: "different-account" }))).toBe(false);
    expect(rolesForSubject("naver:google-user-123")).toEqual([]);
  });

  it("revokes the next session evaluation when a subject is removed", () => {
    vi.stubEnv("AUTH_ADMISSION_MODE", "restricted");
    vi.stubEnv("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON", '{"google:123":["viewer"]}');
    expect(rolesForSubject("google:123")).toEqual(["viewer"]);
    vi.stubEnv("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON", "{}");
    expect(rolesForSubject("google:123")).toEqual([]);
  });

  it("fails closed for missing directories and invalid admission modes", () => {
    vi.stubEnv("AUTH_ADMISSION_MODE", "restricted");
    expect(rolesForSubject("google:123", "")).toEqual([]);
    vi.stubEnv("AUTH_ADMISSION_MODE", "restrcted");
    expect(() => rolesForSubject("google:123", "{}")).toThrow(/AUTH_ADMISSION_MODE/);
  });
});

describe("safe authentication callbacks", () => {
  it("preserves same-origin relative destinations", () => {
    expect(safeAuthCallbackUrl("/drug-letters?category=Laboratory#source")).toBe(
      "/drug-letters?category=Laboratory#source",
    );
  });

  it("rejects absolute, protocol-relative, and malformed destinations", () => {
    expect(safeAuthCallbackUrl("https://attacker.example/path")).toBe("/dashboard");
    expect(safeAuthCallbackUrl("//attacker.example/path")).toBe("/dashboard");
    expect(safeAuthCallbackUrl(["/dashboard"])).toBe("/dashboard");
  });
});
