# PharmaAgent OS — UX source of truth

- Status: active
- Owner: product team
- Last updated: 2026-09-08

## Beginner AI flow — 2026-09-08

This supersedes the draft-first home below now that hosted FDA data and AI answers
work. `/dashboard` leads to `/ask` with a single primary action, three editable
example tasks, and a short question → AI research → source check explanation.
Examples use fixed IDs in URLs and never send requests automatically. The five
everyday destinations are Home, Ask the AI, FDA letters, saved sources and help.
Chat defaults to automatic settings; advanced search/model choices expand on demand.
The question field and send/stop buttons have visible labels. Loading and failure
copy describes progress and recovery in plain Korean/English.

`/requests` retains the complete local draft workflow and the same storage keys.
Old `/dashboard#saved-requests` bookmarks redirect there. Drafts remain unsubmitted.
Specialist tools remain under the expandable menu. Help reflects the connected
source library and cited answers while distinguishing scheduled ingestion and
internal/specialist analysis, which remain unavailable.

## Employee task flow — previous contract, 2026-09-08

This update supersedes the workflow-first home described below. The employee path
is task selection, an editable question, an optional FDA source URL, and an explicit
save/download action. Examples require a user click and do not replace entered
questions. Requests are browser drafts, not submitted cases or agent outputs.
Saved requests can be reopened, updated and deleted; older drafts migrate.
The main export is readable text, with JSON available as a secondary action.

Six everyday navigation destinations lead to review preparation, FDA letters,
evidence questions, saved sources, saved requests and help. Advanced tools remain
in a collapsible section. `/help` explains the first task, current availability,
where drafts are stored and the human decision boundary in Korean and English.
The home describes three agent outcomes; the detailed workflow is optional.

All unavailable states should name the unavailable task and provide a working
recovery action. Do not expose setup details in employee task flows or imply that
this UX update has enabled backend data, company-wide sharing or agent execution.

## Agent workspace redesign — previous contract

At the service owner's request, the whole interface now emphasizes the agentic
review workflow. This section supersedes the former chat-first home and global
shell rules below; detailed FDA research behavior remains applicable.

- `/dashboard` leads with a review objective, local browser draft, and selectable
  nine-step regulatory-impact-review definition. Five specialist agent definitions,
  two human checkpoints, and deterministic validation/composition are distinct.
- Selecting a step explains its responsibility, inputs, output, and workflow tools.
  The displayed definition is explicitly not executing.
- `/agents` offers a searchable team roster and a detail inspector. Versioned
  definitions do not assert live readiness or completed qualification.
- Navigation prioritizes agent work, cases/runs, human review, evaluation, and
  operations. Research chat, FDA evidence, saved research, and trends follow.
- `/ask` retains research chat. Legacy `/dashboard?letter=…`, company and new-chat
  links preserve their context through redirects to `/ask`.
- Local drafts save, restore, delete, and export on the browser only. A local
  confirmation is never described as server persistence or agent execution.
- Live outages and permission denials have explicit recovery paths; no fabricated
  case counts or run progress are substituted. Public viewers retain their guards.
- No account login; Korean default with English switch; keyboard navigation,
  responsive sidebar, visible focus, reduced motion, and single main landmark.
- `DESIGN.md` records the navy navigation, light work surface, cobalt controls,
  and retained Daewoong organizational attribution. CSS zoom is removed.

This document consolidates the product and UX decisions supplied during development. It is the acceptance contract for the current service. It supersedes older presentation and navigation guidance in the industrial handover; the handover's security, provenance, regulatory, and architecture controls remain authoritative.

## Product promise

The service helps Daewoong Pharmaceutical and Daewoong Bio staff find, understand, compare, and follow FDA Drug warning letters without losing the official source. It is decision support, not a compliance conclusion. Every derived answer must make its evidence and limitations visible.

## Experience principles

1. Korean is the default interface language. English remains available everywhere through one consistent language control. Official FDA names, citations, and source text may remain English when translation would reduce precision.
2. Chat is the home page and primary workflow. Search, filters, letter selection, citations, and follow-up questions should feel like one continuous research session.
3. The live service and local preview dataset must never be silently mixed. A preview is visibly labelled; a configured live service fails closed when authoritative data cannot be loaded.
4. A successful action needs a durable confirmation: record ID, job ID, revision, or saved state. A button may not claim completion when the backend only accepted or failed to confirm the work.
5. Controls that have no implementation or destination are not rendered as active controls.
6. The interface is calm and practical: readable type, restrained Daewoong orange, clear hierarchy, consistent page guides, responsive layouts, and no decorative dashboard density.

## Global shell

- The Daewoong Bio logo is used in the sidebar.
- The sidebar is called **Menu**, collapses to the left, and preserves an understandable icon-only state.
- **Chat history** sits below Menu, is independently collapsible, and supports keyword search.
- The same **About this page** control occupies the same content-header position on every page.
- Long marketing headers and page subtitles stay inside the page guide rather than consuming the working canvas.
- Korean labels appear first by default; switching to English updates all navigation, actions, empty states, errors, hints, and accessibility labels.
- Keyboard focus is visible. Dialog focus is trapped and restored. Touch targets remain usable at phone widths.

## Chat

### Landing state

- A new chat fits in the available desktop viewport without an internal scrollbar.
- The landing caption and four suggested questions vary per new thread. The suggestion library contains at least 50 useful pharmaceutical/regulatory prompts.
- The composer is always visible. The landing page starts scrolling only after conversation content needs more space.
- A new thread is not persisted until the user sends a message.

### Conversation state

- Answers stream quickly and visibly. Provider text is labelled as a provisional draft until the complete answer passes language/citation validation and is saved; the committed answer then replaces the draft exactly. Provisional text is never stored and cannot expose active citations or copy controls. The user can stop generation.
- Streaming, stopped, failed, insufficient-evidence, and complete states are distinct and actionable.
- Assistant output renders safe Markdown. Citations are never invented from preview content.
- Every grounded answer exposes source cards with company, document type, source anchor or section, version identity when available, excerpt, and direct FDA link.
- The user can select relevant retrieved documents. Selected documents become the primary evidence scope for that thread until the user changes or clears the focus.
- Opening **Ask** from a warning letter starts a focused chat with the original document immediately. Findings or summary artifacts enrich the context when available but are never prerequisites.

### Retrieval and model routing

- Auto mode decides whether a turn needs no retrieval, metadata lookup, one-letter retrieval, multi-letter comparison, or corpus-wide agentic retrieval.
- Conversational and navigation questions do not trigger a corpus search by default.
- Questions about a known warning letter retrieve that letter's chunks. Internal-pipeline comparison questions use the focused letter evidence plus the user's stated internal context and clearly separate FDA facts from internal interpretation.
- Users can choose Fast, Balanced, or Deep; Auto remains the default and explains the effective model and retrieval route in a compact disclosure.
- Conversation threads and messages are persisted per authenticated user. Every portal route requires a verified Google or valid Naver OAuth identity; public accounts receive viewer access, privileged roles remain server-assigned, and the application never stores a separate password or provider token.

## Drug Letters

### Explorer

- All active scraped warning letters are accessible through backend pagination. Page-size choices include 20, 50, and 100.
- Search state is represented in the URL. Refreshing, sharing, saving, or returning to the page preserves filters, dates, sort, page, and page size.
- Search filters include a clear reset action, query, classification, category, country, lifecycle, review state, linked documents when available, and posted-date range.
- Filters with no meaningful alternative are disabled or omitted rather than pretending to refine results.
- Results can be sorted by posted date, issued date, or company.
- Each result has one unambiguous direct-FDA action. It opens that letter's canonical FDA URL.
- The redundant per-card product label and separator dash are removed. Classification and lifecycle use compact space.
- Field values provide newcomer-friendly hints such as **Warning Letter Subject**, **Issuing Office**, and **Recipient Country**.
- A **NEW** badge appears only during the first seven calendar days after posting.
- Recipient country is parsed from the Recipient address block, including the final country line, and stored as normalized metadata.

### Letter detail

- The only primary tabs are **Original → Findings → Summary → Ask**.
- The title and metadata are compact; findings and summary receive the working space.
- Original preserves headings and bold paragraph subtitles and provides a left-side jump index.
- **Translate to Korean** creates a faithful, clearly labelled AI translation with the original structure. The prompt forbids omission, added advice, or softened language. A successful result is versioned and cached by source version.
- **Generate findings** extracts complete findings into a readable structure in English or Korean, shows provenance, and caches each language artifact by source version.
- **Generate summary** produces an English or Korean brief covering the warning letter's significance and practical attention points for Daewoong teams without asserting an internal compliance conclusion. Each language is versioned and cached.
- Translation, findings, and summary jobs are independently pending. A user can start another artifact or language while earlier generation continues, and equal analysis work is coalesced server-side.
- Generated artifacts expose pending, success, failure, retry, model/prompt version, source version, and saved-state information.
- The FDA source button uses recognizable FDA styling/logo while making clear that the destination is external.

## Trends

- Period controls (30, 90, and 365 days) use actual issue/post dates and display the exact current and comparison periods.
- Counts, distributions, and comparisons are calculated from the connected corpus, never from seed values combined with live records.
- Every meaningful chart/list value drills into Drug Letters with matching URL filters.
- Empty periods show an honest empty state. Missing prior data is not represented as a fabricated zero trend.

## Saved views and alerts

- Saved views are durable backend records owned by the authenticated user, not component-local toggles.
- Creating a view from Drug Letters pre-fills the current canonical filters. Users can create, rename, update criteria/cadence, open, and delete a view.
- Immediate alerts enqueue matching new/updated letters only when notification delivery is operational.
- Daily and weekly cadence may be stored, but the UI must state when a digest scheduler is not yet connected.
- SMTP unavailable, scheduler unavailable, preview-only, disabled, and ready states are visually and verbally distinct.

## Review

- Reviewer edits are stored as a new immutable summary revision; the prior revision remains available.
- A decision records actor, reason, before/after content, source document version, request ID, time, and resulting revision.
- Stale or superseded reviews fail with a conflict instead of overwriting newer work.
- Open, high-attention, and all views, page size, refresh, and cursor pagination are functional.
- Terminal decisions are read-only. Unsaved drafts are protected when switching records or leaving.
- Missing confidence is shown as **not provided**, never converted into a misleading zero.

## Administration

- The first screen is limited to quick operational settings: email recipient and enabled state, SMTP readiness, rolling corpus window, sync action, AI model, and delivery state.
- Email settings distinguish subscription enabled from sender configured and actual delivery enabled.
- Corpus sync and reprocessing return and display their backend run/job IDs.
- Reprocessing accepts either the internal UUID or MARCS-CMS number.
- Advanced status renders only observations returned by the backend. Backup, restore, leakage, SIEM, or control claims are never inferred from placeholders.
- Unsupported evidence links and runbook buttons are omitted or explicitly unavailable.

## System states

| State | Required experience |
|---|---|
| Live and ready | Normal controls; backend-confirmed data and receipts |
| Live but dependency unavailable | Clear cause, affected feature, retry or setup guidance; no preview substitution |
| Empty corpus/result | Valid empty state with filters/reset where relevant |
| Preview | Persistent preview label; isolated sample data; destructive/operational actions disabled |
| Pending async work | Accepted state plus durable job/artifact ID; refreshable status |
| Provisional streaming draft | Clearly labelled unverified text; reset rejected retries; no persistence, active citations, or completion controls until validation succeeds |
| Failed async work | Failure detail safe for users, retry action, correlation/request ID when available |
| Insufficient evidence | No confident answer; show attempted scope and useful next action |

## Release acceptance checklist

- Korean-first and English mode are complete on modified workflows.
- Desktop landing chat does not scroll; mobile has no horizontal overflow.
- Chat streams, stops, retries, restores history, and opens every cited FDA URL.
- Explorer URL state, reset, date range, sort, pagination, page size, and saved-view handoff survive refresh.
- One live API failure cannot produce a screen containing seed records labelled as live.
- Saved views and review edits survive a server-render/navigation round trip.
- Admin email, sync, and reprocess actions show backend-confirmed state and IDs.
- Automated type, lint, build, API, and migration tests pass.
- Representative desktop and phone screenshots are inspected before release.
