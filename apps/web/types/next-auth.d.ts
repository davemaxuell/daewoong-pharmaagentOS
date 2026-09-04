import type { DefaultSession } from "next-auth";
import type { AppRole } from "@/lib/auth-types";

declare module "next-auth" {
  interface Session {
    user: {
      subject: string;
      roles: AppRole[];
    } & DefaultSession["user"];
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    roles?: AppRole[];
  }
}
