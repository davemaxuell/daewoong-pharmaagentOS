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

export type PortalIdentity = {
  subject: string;
  roles: AppRole[];
};
