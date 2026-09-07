# Public portal and backend identity

The service owner removed account login on 2026-09-07. The portal opens directly
at `/dashboard`. Google/Naver provider integrations, account menus, sign-out,
Auth.js callbacks and provider credentials are removed. `/sign-in` redirects to
`/dashboard` for old bookmarks.

## Anonymous browser sessions

The Next.js proxy automatically creates a signed HttpOnly, SameSite=Lax cookie.
Production uses `__Host-pharma-visitor` with Secure and Path=/ and no Domain.
The cookie contains an opaque `anonymous:<UUID>` subject, no email or profile.
It lasts 30 days. Clearing/expiring it starts a new session; there is no account
recovery or cross-device history. Different browsers do not share saved items.

Set `PORTAL_SESSION_SECRET` to at least 32 random characters in hosted deployments,
using distinct values in Preview and Production. Store it as a Vercel Secret.
Local development alone uses a local-only key when the variable is absent.
No OAuth credentials, callback registrations or user-subject directory are needed.

## Private API connection

The backend still requires authenticated server requests. Configure
`API_SESSION_PRIVATE_KEY`, `API_SESSION_ISSUER`, `API_SESSION_AUDIENCE`, and optional
`API_SESSION_KEY_ID` on the web; configure the matching `OIDC_PUBLIC_KEY`,
`OIDC_ISSUER`, `OIDC_AUDIENCE` and `OIDC_ALGORITHMS=RS256` on the API.
The browser never receives this private key or the backend assertion.

The web issues 90-second `public_session` assertions with only `viewer` authority.
The API checks the anonymous UUID subject and rejects other roles, including
privileges introduced by group mapping. Existing privileged human/service API
identities remain separate; anonymous visitors cannot approve reviews, administer
the system, start governed case runs or grant themselves additional authority.

Private browser data uses the anonymous subject for existing API ownership checks.
The browser cookie is not accepted as an API bearer token: it has a separate key,
algorithm and audience. Same-origin checks remain on mutating browser endpoints.

## Verification

Check that `/` opens the dashboard, `/sign-in` redirects there, and `/api/auth/providers`
returns 404. No account controls or provider buttons should appear on desktop or mobile.
Verify distinct browser sessions, returning-session continuity, tampered/expired
cookie replacement, viewer-only backend assertions and denied privileged actions.
The public website still needs its Supabase backend configuration for live data.
