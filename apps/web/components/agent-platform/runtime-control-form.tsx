"use client";

import { useActionState } from "react";
import {
  EMPTY_CONTROL_ACTION_STATE,
  updateRuntimeControlAction,
} from "@/app/(portal)/control-tower/actions";
import type { InventoryItem, RuntimeControl } from "@/lib/governance-api-client";
import styles from "./governance.module.css";

export function RuntimeControlForm({
  control,
  availableAgents = [],
}: {
  control?: RuntimeControl;
  availableAgents?: InventoryItem[];
}) {
  const [state, action, pending] = useActionState(
    updateRuntimeControlAction,
    EMPTY_CONTROL_ACTION_STATE,
  );
  const scope = control?.scope ?? (availableAgents.length ? "AGENT" : "GLOBAL");
  return (
    <form className={styles.controlForm} action={action}>
      <input type="hidden" name="scope" value={scope} />
      {control ? <input type="hidden" name="expected_revision" value={control.revision} /> : null}
      <div>
        <span>{scope === "GLOBAL" ? "Global execution" : "Exact agent version"}</span>
        <strong>{control?.controlKey ?? "New agent control"}</strong>
        {control ? <small>Revision {control.revision} · {control.updatedBy}</small> : null}
      </div>
      {control?.agentVersionId ? (
        <input type="hidden" name="agent_version_id" value={control.agentVersionId} />
      ) : scope === "AGENT" ? (
        <label>Agent version<select name="agent_version_id" required>{availableAgents.map((agent) => <option key={agent.id} value={agent.id}>{agent.key}@{agent.version}</option>)}</select></label>
      ) : null}
      <label>State<select name="suspended" defaultValue={control?.suspended ? "true" : "false"}><option value="false">Active</option><option value="true">Suspended</option></select></label>
      <label>Reason<input name="reason" minLength={8} maxLength={2_000} defaultValue={control?.reason} required /></label>
      <button type="submit" disabled={pending}>{pending ? "Recording…" : "Record control"}</button>
      {state.message ? <p className={state.status === "error" ? styles.error : styles.success}>{state.message}</p> : null}
    </form>
  );
}
