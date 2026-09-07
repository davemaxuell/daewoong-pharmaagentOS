# PharmaAgent OS web interface

Next.js App Router workspace for agent-assisted regulatory review. The home page
emphasizes review objectives, specialist responsibilities, evidence, and human
checkpoints. FDA research supports the agent workspace.

- `/dashboard`: local review brief, interactive nine-step workflow, accessible case activity.
- `/agents`: five versioned agent definitions with search and a responsibility inspector.
- `/cases`, `/approvals`, `/evaluations`, `/control-tower`: governed work and oversight.
- `/ask`: research chat; old dashboard links with letter/company/new parameters redirect here.
- `/drug-letters`, `/saved-views`, `/trends`: supporting evidence research.

The shared visual system is recorded in `../../DESIGN.md`. Local briefs are stored
in this browser and export as explicitly unexecuted JSON; they do not create a
case or start an agent run. Backend execution and data readiness remain separate.

```bash
npm install
npm run dev
```

Set `API_BASE_URL` to connect the server-rendered portal to the FastAPI service.
When the variable is absent, legacy research pages can use the explicitly labeled
local preview dataset. Configured live failures show unavailable states. Agent
case records are never replaced with preview cases or invented execution metrics.

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
