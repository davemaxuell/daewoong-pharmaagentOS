# FDA Drug Warning Letter Intelligence Portal

Next.js App Router portal for the FDA `Product: Drugs` intelligence service.

```bash
npm install
npm run dev
```

Set `API_BASE_URL` to connect the server-rendered portal to the FastAPI service.
When the variable is absent or the service is unavailable, the UI uses the
isolated preview dataset in `lib/seed-data.ts`; the page visibly labels that mode.

The portal opens directly without login, Google/Naver accounts, or OAuth callbacks.
A signed HttpOnly browser cookie isolates each visitor's saved views and chat history;
clearing or expiring it starts a new visitor session. No account/profile data is collected.
Configure `PORTAL_SESSION_SECRET` (at least 32 random characters) for hosted deployments.
Local development uses a local-only key when that variable is absent.

The web signs 90-second RS256 `public_session` assertions for the private API.
Visitors receive only `viewer`; review, administration, and release actions retain
backend authorization. See `../../docs/runbooks/authentication.md` for setup.

Quality checks:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```
