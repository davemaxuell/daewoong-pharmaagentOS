# Beginner AI experience — 2026-09-08

The entry path now reaches working FDA research. Home offers one primary AI action,
three editable examples and a short explanation of asking, AI research and source
checking. The five everyday destinations use familiar task names. Advanced
settings are optional; defaults, source scoping and backend authorization remain.

Personal draft preparation moved intact to `/requests`, retaining the storage
format and keys. Legacy saved-request bookmarks redirect there. Source/company
deep links still reach the correct research context. Examples carry fixed task IDs
and prefill the composer without sending a request.

The Korean/English guide now describes the connected library and cited answers,
where to find previous work, follow-up questions and recovery steps. It clearly
distinguishes automatic FDA refresh and internal/specialist analysis, which remain
unavailable. Chat progress and errors use plain language. Visible question and
send labels also supply their accessible names.

## Local validation

- Production build and TypeScript passed.
- Full frontend lint passed; the final accessible-name adjustment also passed
  focused lint and a rebuilt production bundle.
- All 26 existing frontend tests passed.
- 26 browser checks passed on the final production bundle: Korean/English home,
  chat and help at 320, 390, 768 and 1440px; no horizontal overflow; desktop sidebar
  clearance; send-button label containment; examples, unknown task IDs, no automatic
  send, optional settings, filter disclosure, Escape/focus, local draft persistence
  and legacy bookmarks. No JavaScript errors.
- The design detector reported existing legacy global-CSS rules only, with no
  findings in newly added UI code. Those unrelated styles were preserved.

Screenshots and check scripts/results: `.artifacts/beginner-ux-20260908/` (ignored).
Viewport screenshots and DOM bounds were used for visual verification because
this Edge build shifts fixed-sidebar layouts during full-page capture.

## Publication

Feature revision: `ab22a41`. Accessible-name follow-up: `81f3e9b`.
Both revisions deployed successfully. Revision `81f3e9b` passed all GitHub quality
and security jobs and the 26 hosted browser checks; database/Storage readiness was
healthy. An actual Korean example request completed with six source references,
but its model metadata reported `generation_used=false` and `fallback=source_facts`.
This is evidence retrieval, **not a successful AI-generated explanation**.

That observation prompted a final fallback UX change: a plain-language explanation,
retry/source guidance and closed original-excerpt disclosure replace the immediate
long raw-English response. Citations remain accessible and the underlying response
is preserved. Three rendering regressions cover fallback disclosure, successful AI
answers and the no-source case; all 29 frontend tests, build and focused lint pass.
Final application revision `d25d5cb` is deployed successfully. A real Korean
document-specific question about Safrel Pharmaceuticals LLC completed with an
AI-generated answer (`gpt-5-mini` shown in the response record), six cited sources
and no browser JavaScript errors. The saved conversation remained readable after
navigation. This successful generation is distinct from the earlier generic
source-only fallback. Database and Storage readiness remained healthy.

Final revision CI: code-security run `34218188041` passed. In quality run
`34218187942`, frontend, contracts, schema, container, recovery, secret-scan and
deployment-render jobs passed; the unchanged backend suite was still running when
this record was written. No failed jobs were reported. The preceding full quality
run for `81f3e9b` passed. No backend code or hosting credentials changed in this UX task.
