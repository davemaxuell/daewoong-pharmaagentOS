# FDA Drug Warning Letter Intelligence Portal

Next.js App Router portal for the FDA `Product: Drugs` intelligence service.

```bash
npm install
npm run dev
```

Set `API_BASE_URL` to connect the server-rendered portal to the FastAPI service.
When the variable is absent or the service is unavailable, the UI uses the
isolated preview dataset in `lib/seed-data.ts`; the page visibly labels that mode.

All portal access requires Google or Naver through Auth.js. Configure at least one
provider together with `AUTH_SECRET` and register its exact callback:

```text
https://YOUR_DOMAIN/api/auth/callback/google
https://YOUR_DOMAIN/api/auth/callback/naver
```

Public admission mode gives verified Google and valid Naver identities viewer access.
For private deployments, set `AUTH_ADMISSION_MODE=restricted` and explicitly assign
each admitted subject in `AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON`, including viewers.
An empty restricted directory denies everyone. Email configuration cannot grant access or roles.
Provider tokens are not forwarded to FastAPI. The web server uses the separate
short-lived RS256 application assertion described in `.env.example`.

See `../../docs/runbooks/authentication.md` for provider-console, key, staging, and
verification steps.

Quality checks:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```
