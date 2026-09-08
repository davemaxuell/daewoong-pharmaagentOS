---
name: PharmaAgent OS — Review workbench
colors:
  primary: "#3159c9"
  ink: "#192438"
  muted: "#596779"
  surface: "#ffffff"
  canvas: "#f3f5f9"
  navigation: "#172235"
  rule: "#dce2ec"
  brand: "#f18a00"
rounded:
  control: "8px"
  panel: "14px"
spacing:
  small: "8px"
  medium: "16px"
  large: "24px"
---

## Overview

An employee-facing review assistant. The main path is giving the FDA Research Agent
a goal, following its saved actions and reviewing a cited brief. Quick AI chat
remains available for short questions. Editable examples help beginners
start without model configuration. Keep the navy/light/cobalt
identity and the enlarged, readable type scale.

## Colors

Restrained color: light work surfaces for long document review under office
lighting; navy navigation separates persistent wayfinding from task content.
Cobalt indicates selected steps and primary actions. Orange retains Daewoong
attribution. Semantic amber means a dependency is unavailable, never active work.

## Typography

Use the existing locally hosted Pretendard variable font for Korean and English.
Primary body text 17–19px, supporting text 14–15px, small metadata at least 13px,
and workspace page titles 33–40px. Use rem sizes to respect browser font settings.
No global CSS zoom. Main controls are 44–50px tall; workflow rows start at 60px.
Use monospace only for hashes, identifiers, and machine-readable values.

## Layout

A 280px navigation rail, 76px contextual header, and a bounded content canvas.
The home has one primary research entry, three quick-chat example rows and a short
visual sequence: You set the goal → Research agent finds and checks → You review
the brief. Use the shared journey on Home and Help, and its compact variant above
the research goal field. Personal review drafts remain at
`/requests`; legacy saved-request bookmarks redirect there. Everyday navigation
has six destinations. Specialist tools, drafts and operational tools
expand in a separate section, automatically open on their active routes.

## Elevation & Depth

Panels use a single subtle border. Reserve shadows for floating navigation and
overlays; no glowing edges or decorative grids.

## Shapes

Eight-pixel controls and fourteen-pixel panels. Small status badges may be pills.
Workflow connectors indicate actual step ordering, not animated execution.

## Components

Research starts with a labeled goal and editable examples. Actual persisted events
drive the stage indicator and activity feed; show no simulated progress or hidden
reasoning. Source rows disclose the exact retained passages. Stop revokes ongoing
work, Resume continues saved progress, and a prominent View brief action leads to
the checked draft and copy/download controls. State clearly that tasks are saved
on the service and accessed through the same browser session. Completed briefs
remain drafts for human review. Keep the two-column activity/evidence view readable
as a single column on narrow screens.

Prefer short verb labels and labeled icons to repeated instructional paragraphs.
Show the latest four recorded actions first, with an explicit full-history toggle.
Plans, scope/storage details and review notes expand on demand with native keyboard
controls. Keep source scope and human-review status visible. Never shorten the
generated findings, source excerpts or exported brief to reduce interface copy.

Chat has a labeled question field and a text send button. Model and retrieval
controls expand on demand, with automatic defaults. Example IDs prefill questions
without automatically sending them. Saved-source scope remains visible.
Draft inputs use native radio controls, visible labels and an optional FDA link.
An example fills only an empty question. Multiple local requests can be saved,
reopened, updated, deleted with confirmation and downloaded as readable text;
JSON is secondary. Previous single drafts migrate without losing their question.
Every receipt identifies the request as unsubmitted and not analyzed. A compact
availability notice and a getting-started guide explain the current limits.
Missing data has plain-language recovery actions instead of technical errors.
Keyboard focus is visible. Reduced motion removes optional transitions.

## Do's and Don'ts

Preserve existing research, case, review, and governance capabilities and guards.
No account controls. No invented run counts or fabricated successful agent work.
Keep the review objective, evidence provenance, and next action visible.
