import NextAuth from "next-auth";
import Google, { type GoogleProfile } from "next-auth/providers/google";
import Naver, { type NaverProfile } from "next-auth/providers/naver";
import {
  googleSubject,
  isAllowedGoogleProfile,
  isAllowedNaverProfile,
  isTrustedAuthSubject,
  naverSubject,
  normalizeEmail,
  rolesForSubject,
} from "@/lib/auth-policy";

export {
  isAllowedEmail,
  isAuthRequired,
  isGoogleSubject,
  isNaverSubject,
  isTrustedAuthSubject,
  providerForSubject,
  rolesForEmail,
  rolesForSubject,
} from "@/lib/auth-policy";

export function isGoogleAuthConfigured() {
  return Boolean(
    process.env.AUTH_SECRET &&
      process.env.AUTH_GOOGLE_ID &&
      process.env.AUTH_GOOGLE_SECRET,
  );
}

export function isNaverAuthConfigured() {
  return Boolean(
    process.env.AUTH_SECRET &&
      process.env.AUTH_NAVER_ID &&
      process.env.AUTH_NAVER_SECRET,
  );
}

export function isAuthConfigured() {
  return isGoogleAuthConfigured() || isNaverAuthConfigured();
}

const providers = [];

if (isGoogleAuthConfigured()) {
  providers.push(
    Google<GoogleProfile>({
      checks: ["pkce", "state"],
      authorization: {
        params: {
          prompt: "select_account",
          scope: "openid email profile",
        },
      },
      profile(profile) {
        const subject = googleSubject(profile.sub);
        if (!subject) {
          throw new Error("Google did not return a valid immutable subject.");
        }

        return {
          id: subject,
          name: profile.name ?? null,
          email: normalizeEmail(profile.email) || null,
          image: profile.picture ?? null,
        };
      },
    }),
  );
}

if (isNaverAuthConfigured()) {
  providers.push(
    Naver<NaverProfile>({
      checks: ["state"],
      profile(profile) {
        const subject = naverSubject(profile.response?.id);
        if (!subject) {
          throw new Error("Naver did not return a valid immutable subject.");
        }

        return {
          id: subject,
          name: profile.response.name ?? profile.response.nickname ?? null,
          email: normalizeEmail(profile.response.email) || null,
          image: profile.response.profile_image ?? null,
        };
      },
    }),
  );
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers,
  pages: {
    signIn: "/sign-in",
    error: "/sign-in",
  },
  session: {
    strategy: "jwt",
    maxAge: 8 * 60 * 60,
  },
  callbacks: {
    async signIn({ account, profile }) {
      if (!account || !profile) return false;
      if (account.provider === "google") {
        return isAllowedGoogleProfile(profile as GoogleProfile);
      }
      if (account.provider === "naver") {
        return isAllowedNaverProfile(profile as NaverProfile);
      }
      return false;
    },
    async jwt({ token, account, profile, user }) {
      if (account) {
        if (!profile) return token;
        if (account.provider === "google") {
          const googleProfile = profile as GoogleProfile;
          const subject = googleSubject(googleProfile.sub);
          if (!subject || googleProfile.email_verified !== true) return token;

          token.sub = subject;
          token.name = user.name ?? googleProfile.name ?? null;
          token.email = normalizeEmail(user.email ?? googleProfile.email) || null;
          token.picture = user.image ?? googleProfile.picture ?? null;
        } else if (account.provider === "naver") {
          const naverProfile = profile as NaverProfile;
          const subject = naverSubject(naverProfile.response?.id);
          if (!subject || !isAllowedNaverProfile(naverProfile)) return token;

          token.sub = subject;
          token.name = user.name ?? naverProfile.response.name ?? naverProfile.response.nickname ?? null;
          token.email = normalizeEmail(user.email ?? naverProfile.response.email) || null;
          token.picture = user.image ?? naverProfile.response.profile_image ?? null;
        } else {
          return token;
        }
      }

      if (isTrustedAuthSubject(token.sub)) {
        token.roles = rolesForSubject(token.sub);
      } else {
        token.roles = [];
      }
      return token;
    },
    async session({ session, token }) {
      const subject = isTrustedAuthSubject(token.sub) ? token.sub : "";
      return {
        expires: session.expires,
        user: {
          subject,
          name: typeof token.name === "string" ? token.name : null,
          email: typeof token.email === "string" ? token.email : null,
          image: typeof token.picture === "string" ? token.picture : null,
          roles: subject ? rolesForSubject(subject) : [],
        },
      };
    },
    async redirect({ url, baseUrl }) {
      try {
        const base = new URL(baseUrl);
        const destination = new URL(url, base);
        if (destination.origin === base.origin) return destination.toString();
      } catch {
        // Invalid and cross-origin callback values both fall back to the portal.
      }
      return new URL("/dashboard", baseUrl).toString();
    },
  },
});
