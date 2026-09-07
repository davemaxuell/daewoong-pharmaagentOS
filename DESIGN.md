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

An operating workbench for pharmaceutical review. A multidisciplinary protocol
board supplies the structure: objective, specialist responsibilities, ordered
steps, evidence outputs, and a human handoff. Replace the former FDA chat landing
page and inconsistent green/orange workspaces with this shared system.

## Colors

Restrained color: light work surfaces for long document review under office
lighting; navy navigation separates persistent wayfinding from task content.
Cobalt indicates selected steps and primary actions. Orange retains Daewoong
attribution. Semantic amber means a dependency is unavailable, never active work.

## Typography

Use the existing locally hosted Pretendard variable font for Korean and English.
Body 14–16px, labels 12–13px, page titles 30–36px. No global CSS zoom.
Use monospace only for hashes, identifiers, and machine-readable values.

## Layout

A 244px navigation rail, 68px contextual header, and a bounded content canvas.
The home places a task brief beside a specialist workflow and inspector. Lower
sections expose real case status and supporting research. On narrow screens the
rail becomes an accessible drawer, the task precedes the plan, and details stack.

## Elevation & Depth

Panels use a single subtle border. Reserve shadows for floating navigation and
overlays; no glowing edges or decorative grids.

## Shapes

Eight-pixel controls and fourteen-pixel panels. Small status badges may be pills.
Workflow connectors indicate actual step ordering, not animated execution.

## Components

Task inputs have visible labels. Template controls fill editable objectives.
Selecting a workflow step reveals its responsibility, inputs, outputs, and tools.
Local drafts are explicitly identified and editable; no simulated run is presented
as a live case. Missing data is an unavailable state, not an empty count.
Keyboard focus is visible. Reduced motion removes optional transitions.

## Do's and Don'ts

Preserve existing research, case, review, and governance capabilities and guards.
No account controls. No invented run counts or fabricated successful agent work.
Keep the review objective, evidence provenance, and next action visible.
