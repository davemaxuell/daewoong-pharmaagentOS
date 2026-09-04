"use server";

import { revalidatePath } from "next/cache";
import { getPortalIdentity } from "@/lib/backend-auth";
import { GovernanceApiError, updateRuntimeControl } from "@/lib/governance-api-client";

export type ControlActionState = { status: "idle" | "success" | "error"; message?: string };
export const EMPTY_CONTROL_ACTION_STATE: ControlActionState = { status: "idle" };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function value(data: FormData, name: string, max = 2_000) {
  const raw = data.get(name);
  return typeof raw === "string" ? raw.trim().slice(0, max) : "";
}

export async function updateRuntimeControlAction(
  _state: ControlActionState,
  data: FormData,
): Promise<ControlActionState> {
  const identity = await getPortalIdentity();
  if (!identity.roles.some((role) => role === "platform_admin" || role === "system_owner")) {
    return { status: "error", message: "A Platform Administrator or System Owner role is required." };
  }
  const scope = value(data, "scope", 20);
  const agentVersionId = value(data, "agent_version_id", 36);
  const reason = value(data, "reason");
  const expected = value(data, "expected_revision", 20);
  if (!reason || reason.length < 8 || !["GLOBAL", "AGENT"].includes(scope)) {
    return { status: "error", message: "A bounded control reason is required." };
  }
  if (scope === "AGENT" && !UUID.test(agentVersionId)) {
    return { status: "error", message: "Select an exact agent version." };
  }
  const target: "global" | `agents/${string}` =
    scope === "GLOBAL" ? "global" : `agents/${agentVersionId}`;
  try {
    await updateRuntimeControl(target, {
      suspended: value(data, "suspended", 8) === "true",
      reason,
      ...(expected ? { expected_revision: Number(expected) } : {}),
    });
  } catch (error) {
    return {
      status: "error",
      message: error instanceof GovernanceApiError ? error.message : "The runtime control was not changed.",
    };
  }
  revalidatePath("/control-tower");
  return { status: "success", message: "Runtime control revision recorded and enforced." };
}
