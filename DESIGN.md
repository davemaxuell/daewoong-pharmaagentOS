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

An employee-facing review assistant. The main path is asking a question, reading
the AI answer and checking its source references. Editable examples help beginners
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
The home has one primary AI entry, three example task rows and a short explanation
of asking, AI research and source checking. Personal review drafts remain at
`/requests`; legacy saved-request bookmarks redirect there. Everyday navigation
has five destinations. Specialist tools, drafts and operational tools
expand in a separate section, automatically open on their active routes.

## Elevation & Depth

Panels use a single subtle border. Reserve shadows for floating navigation and
overlays; no glowing edges or decorative grids.

## Shapes

Eight-pixel controls and fourteen-pixel panels. Small status badges may be pills.
Workflow connectors indicate actual step ordering, not animated execution.

## Components

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
