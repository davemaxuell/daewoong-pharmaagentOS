# Google and Naver authentication

All portal pages, application API routes, and Server Actions require an authenticated
Google or Naver identity. There is no application password or unauthenticated local
portal mode.

## Account policy

- A Google profile must contain an immutable subject, a returned email, and
  `email_verified=true`.
- A Naver profile must return a successful result, immutable provider ID, and a
  consented email. The email may use any domain because the account key is the Naver ID.
- Every unassigned Google or Naver identity receives `viewer`.
- Privileged roles are assigned only by immutable provider subject in a private,
  server-side role directory. Email configuration never grants authority.
- Google and Naver subjects are separate accounts. Never merge them based only on a
  matching email.
- Provider access, refresh, and ID tokens must not be forwarded to FastAPI or stored in
  the service database.

## Provider applications

Create separate web OAuth applications in Google Cloud Console and Naver Developers.
Register every callback exactly, including scheme, hostname, port, and path.

Local callbacks:

```text
http://localhost:3000/api/auth/callback/google
http://localhost:3000/api/auth/callback/naver
```

Production callbacks:

```text
https://YOUR_DOMAIN/api/auth/callback/google
https://YOUR_DOMAIN/api/auth/callback/naver
```

Configure the Google consent screen for external users and publish the production
homepage, privacy policy, and terms pages on the verified application domain. Configure
Naver to return the profile ID and email attributes and complete any provider review
required before public release.

## Web configuration

Copy `apps/web/.env.example` to the ignored local or deployment environment and set:

```text
AUTH_SECRET=<generated Auth.js secret>
AUTH_URL=https://YOUR_DOMAIN
AUTH_GOOGLE_ID=<server-side client ID>
AUTH_GOOGLE_SECRET=<server-side client secret>
AUTH_NAVER_ID=<server-side client ID>
AUTH_NAVER_SECRET=<server-side client secret>
```

Generate `AUTH_SECRET` with `npx auth secret`. Do not commit any value produced by that
command. For local development, use `AUTH_URL=http://localhost:3000`.

No email allowlist or privileged-email list is used. Provider verification establishes
email ownership. Unassigned accounts receive `viewer`. To assign governed workflow
roles, set a private JSON object whose keys are exact provider subjects:

```text
AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON={"google:0123456789":["analyst"],"naver:abc123":["reviewer"]}
```

Supported human application roles are `viewer`, `analyst`, `reviewer`, `domain_sme`,
`agent_developer`, `platform_admin`, `system_owner`, `admin`, and `auditor`. The parser
rejects malformed JSON, email keys, unknown or duplicate roles, empty assignments, and
oversized directories. Keep this value in the deployment secret/configuration system;
do not expose it through a `NEXT_PUBLIC_*` variable. Role changes take effect when the
server evaluates the session and signs the next short-lived API assertion.

## Web-to-API assertion

Generate a dedicated RSA keypair. Keep the PKCS#8 private key only in the web service and
the public key only in the API service.

```powershell
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out web-session-private.pem
openssl pkey -in web-session-private.pem -pubout -out web-session-public.pem
```

Web settings:

```text
API_SESSION_PRIVATE_KEY=<private PEM with literal newlines encoded as \\n when required>
API_SESSION_KEY_ID=web-session-v1
API_SESSION_ISSUER=daewoong-fda-web
API_SESSION_AUDIENCE=daewoong-fda-api
```

API settings:

```text
DEV_AUTH_ENABLED=false
OIDC_ISSUER=daewoong-fda-web
OIDC_AUDIENCE=daewoong-fda-api
OIDC_PUBLIC_KEY=<matching public PEM>
OIDC_ALGORITHMS=["RS256"]
```

The web assertion expires after 90 seconds. Provider tokens never cross this boundary.

## Verification

1. Open a protected deep link in a signed-out browser and confirm it redirects to
   `/sign-in` with a relative callback.
2. Complete Google login and confirm the original deep link opens with viewer access.
3. Repeat with Naver using an account that consents to email return.
4. Confirm an unverified Google email, missing Naver email, malformed provider subject,
   and cross-origin callback are rejected.
5. Confirm an unassigned account receives only viewer access, then assign roles by its
   exact provider subject and verify the corresponding server actions and signed API
   assertion. Confirm email-only configuration never changes roles.
6. Confirm direct signed-out POSTs to chat and document-generation routes return `401`.
7. Use two different provider accounts and verify chat threads, saved views, and
   subscriptions never cross account subjects.
8. Sign out and confirm the previous protected URL requires authentication again.
9. Run `npm test`, `npm run lint`, `npm run typecheck`, and `npm run build` from
   `apps/web` before release.

## Operational response

Rotate a compromised provider secret in its provider console and deployment secret
manager, then restart the web service. Rotate `AUTH_SECRET` to invalidate every Auth.js
session. Rotate the RSA keypair by publishing the new API public key before switching the
web key ID/private key. Record privileged-role changes and account-abuse investigations
in the retained audit/SIEM workflow.
