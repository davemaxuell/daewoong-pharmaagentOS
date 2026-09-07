import { NextResponse, type NextRequest } from "next/server";
import {
  createVisitorSession, readVisitorSession, visitorCookieName, VISITOR_SESSION_SECONDS,
} from "@/lib/visitor-session";

export async function proxy(request: NextRequest) {
  const name = visitorCookieName();
  const existing = request.cookies.get(name)?.value;
  const subject = await readVisitorSession(existing);
  const token = subject ? existing! : await createVisitorSession();
  // Forward the first cookie to Server Components before storing it in the browser.
  request.cookies.set(name, token);
  const response = NextResponse.next({ request: { headers: request.headers } });
  response.headers.set("Cache-Control", "private, no-store");
  if (!subject) {
    response.cookies.set(name, token, {
      httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax",
      path: "/", maxAge: VISITOR_SESSION_SECONDS,
    });
  }
  return response;
}

export const config = {
  matcher: [
    "/((?!api/health(?:/|$)|_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|css|js|map|woff|woff2|ttf)$).*)",
  ],
};
