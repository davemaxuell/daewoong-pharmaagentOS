import { describe, expect, it } from "vitest";
import {
  caseStatusTone,
  formatCaseStatus,
  isPlanBindingCurrent,
  latestPlanVersion,
  parseAgentCase,
  parseCaseEventPage,
  parseCasePlan,
  shortHash,
} from "@/lib/case-types";

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const HASH_C = "c".repeat(64);
const CASE_ID = "11111111-1111-4111-8111-111111111111";
const SOURCE_ID = "22222222-2222-4222-8222-222222222222";
const DOCUMENT_ID = "33333333-3333-4333-8333-333333333333";
const VERSION_ID = "44444444-4444-4444-8444-444444444444";
const LETTER_ID = "55555555-5555-4555-8555-555555555555";

function casePayload() {
  return {
    id: CASE_ID,
    title: "Sterile manufacturing impact review",
    objective: "Determine potential relevance without making a compliance conclusion.",
    status: "AWAITING_PLAN_APPROVAL",
    owner_subject: "google:analyst@example.com",
    workflow_key: "regulatory-impact-review",
    current_state_hash: HASH_A,
    sources: [
      {
        id: SOURCE_ID,
        case_id: CASE_ID,
        warning_letter_id: LETTER_ID,
        document_id: DOCUMENT_ID,
        document_version_id: VERSION_ID,
        document_version_number: 3,
        source_role: "PRIMARY_REGULATORY",
        source_sha256: HASH_B,
        source_url: "https://www.fda.gov/example",
        pinned_by: "google:analyst@example.com",
        created_at: "2026-09-04T08:00:00Z",
        immutable: true,
      },
    ],
    created_at: "2026-09-04T08:00:00Z",
    updated_at: "2026-09-04T08:05:00Z",
  };
}

function planPayload() {
  return {
    id: "66666666-6666-4666-8666-666666666666",
    case_id: CASE_ID,
    version: 2,
    objective: "Determine potential relevance without making a compliance conclusion.",
    plan_schema_version: "1.0.0",
    plan_sha256: HASH_C,
    based_on_state_hash: HASH_A,
    prohibited_actions: ["UPDATE_QMS_RECORD"],
    created_by: "google:analyst@example.com",
    created_at: "2026-09-04T08:04:00Z",
    steps: [
      {
        id: "77777777-7777-4777-8777-777777777777",
        position: 1,
        step_key: "regulatory_evidence",
        title: "Extract evidence",
        instructions: "Read the exact retained source only.",
        depends_on: [],
        agent_version_id: null,
        skill_version_ids: [],
        tool_version_ids: [],
        output_schema_ref: "urn:example:finding:v1",
        risk_level: "R0",
        requires_approval: false,
        limits: {
          max_turns: 4,
          max_tool_calls: 10,
          max_input_tokens: 100_000,
          max_output_tokens: 20_000,
          max_runtime_seconds: 180,
          max_cost_usd: 2,
        },
        created_at: "2026-09-04T08:04:00Z",
      },
    ],
    approval: {
      id: "88888888-8888-4888-8888-888888888888",
      approval_type: "PLAN_APPROVAL",
      status: "PENDING",
      requested_by: "google:analyst@example.com",
      assigned_reviewer_id: null,
      decision_by: null,
      decision_reason: null,
      decided_at: null,
      expires_at: "2026-09-11T08:04:00Z",
      plan_sha256: HASH_C,
      bound_state_hash: HASH_A,
      created_at: "2026-09-04T08:04:00Z",
    },
  };
}

function event(sequence: number, eventType: string, planVersion?: number) {
  return {
    id: `${sequence.toString().padStart(8, "0")}-9999-4999-8999-999999999999`,
    case_id: CASE_ID,
    sequence,
    event_type: eventType,
    actor_type: "user",
    actor_id: "google:analyst@example.com",
    request_id: `request-${sequence}`,
    payload: planVersion ? { plan_version: planVersion } : {},
    previous_event_hash: sequence === 1 ? null : HASH_B,
    event_hash: HASH_C,
    state_hash: HASH_A,
    occurred_at: "2026-09-04T08:04:00Z",
  };
}

describe("case response contracts", () => {
  it("normalizes exact source pins without losing hashes or identifiers", () => {
    const item = parseAgentCase(casePayload());

    expect(item.status).toBe("AWAITING_PLAN_APPROVAL");
    expect(item.currentStateHash).toBe(HASH_A);
    expect(item.sources[0]).toMatchObject({
      documentVersionId: VERSION_ID,
      documentVersionNumber: 3,
      sourceSha256: HASH_B,
      immutable: true,
    });
  });

  it("rejects a mutable or malformed source response", () => {
    const mutable = casePayload();
    mutable.sources[0].immutable = false;
    expect(() => parseAgentCase(mutable)).toThrow(/immutable must be true/i);

    const malformed = casePayload();
    malformed.current_state_hash = "not-a-hash";
    expect(() => parseAgentCase(malformed)).toThrow(/sha-256/i);
  });

  it("retains approval expiry and verifies the three-way hash binding", () => {
    const agentCase = parseAgentCase(casePayload());
    const plan = parseCasePlan(planPayload());

    expect(plan.approval.expiresAt).toBe("2026-09-11T08:04:00Z");
    expect(isPlanBindingCurrent(plan, agentCase)).toBe(true);

    const changedCase = { ...agentCase, currentStateHash: HASH_B };
    expect(isPlanBindingCurrent(plan, changedCase)).toBe(false);
  });
});

describe("case history helpers", () => {
  it("finds the latest generated plan version and ignores unrelated events", () => {
    const page = parseCaseEventPage({
      items: [
        event(1, "CASE_CREATED"),
        event(2, "PLAN_GENERATED", 1),
        event(3, "PLAN_APPROVAL_EXPIRED"),
        event(4, "PLAN_GENERATED", 3),
      ],
      next_cursor: null,
      has_more: false,
    });

    expect(latestPlanVersion(page.items)).toBe(3);
  });

  it("formats controlled states and hashes consistently", () => {
    expect(formatCaseStatus("AWAITING_PLAN_APPROVAL")).toBe("Awaiting Plan Approval");
    expect(caseStatusTone("NEEDS_REVISION")).toBe("attention");
    expect(shortHash(HASH_A, 6)).toBe("aaaaaa…aaaaaa");
  });
});
