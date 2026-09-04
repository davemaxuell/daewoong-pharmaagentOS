export const APP_ROLES = [
  "viewer",
  "analyst",
  "reviewer",
  "domain_sme",
  "agent_developer",
  "platform_admin",
  "system_owner",
  "admin",
  "auditor",
] as const;

export type AppRole = (typeof APP_ROLES)[number];

export const AUTH_PROVIDERS = ["google", "naver"] as const;

export type AuthProvider = (typeof AUTH_PROVIDERS)[number];

export type PortalIdentity = {
  subject: string;
  name: string | null;
  email: string | null;
  image: string | null;
  provider: AuthProvider;
  roles: AppRole[];
  authenticated: boolean;
};

export type PortalAccount = Pick<
  PortalIdentity,
  "name" | "email" | "image" | "provider" | "authenticated"
>;
