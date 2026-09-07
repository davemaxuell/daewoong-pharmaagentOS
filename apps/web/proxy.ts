import type { NextAuthRequest } from "next-auth";
import {
  NextResponse,
  type NextFetchEvent,
  type NextRequest,
} from "next/server";
import {
  auth,
  isAllowedEmail,
  isAuthConfigured,
  isTrustedAuthSubject,
  rolesForSubject,
} from "@/auth";

function redirectToSignIn(request: NextRequest) {
  const signInUrl = new URL("/sign-in", request.url);
  signInUrl.searchParams.set(
    "callbackUrl",
    `${request.nextUrl.pathname}${request.nextUrl.search}`,
  );
  return NextResponse.redirect(signInUrl);
}

function apiAccessResponse(status: 401 | 503) {
  return NextResponse.json(
    {
      error: status === 401
        ? "Authentication with Google or Naver is required."
        : "Google or Naver authentication is not configured.",
    },
    {
      status,
      headers: { "Cache-Control": "no-store" },
    },
  );
}

function denyAccess(request: NextRequest, status: 401 | 503) {
  return request.nextUrl.pathname.startsWith("/api/")
    ? apiAccessResponse(status)
    : redirectToSignIn(request);
}

const authenticatedProxy = auth((request: NextAuthRequest, _event: NextFetchEvent) => {
  void _event;
  if (
    !request.auth?.user ||
    !isTrustedAuthSubject(request.auth.user.subject) ||
    !isAllowedEmail(request.auth.user.email) ||
    rolesForSubject(request.auth.user.subject).length === 0
  ) {
    return denyAccess(request, 401);
  }
  return NextResponse.next();
});

export function proxy(request: NextRequest, event: NextFetchEvent) {
  if (!isAuthConfigured()) return denyAccess(request, 503);
  return authenticatedProxy(request, event);
}

export const config = {
  matcher: [
    "/((?!api/auth(?:/|$)|api/health(?:/|$)|sign-in(?:/|$)|_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|css|js|map|woff|woff2|ttf)$).*)",
  ],
};
