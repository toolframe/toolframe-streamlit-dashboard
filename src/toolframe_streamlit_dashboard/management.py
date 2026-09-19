"""Thin UI over host management operations, with no installer or database logic."""

import streamlit as st
from toolframe_sdk import PluginError

_PLAN_OPERATION_KEY = "plan_operation_id"
_PLANNED_ACTIONS = {"enable", "reload", "disable", "stop", "remove"}


def render_management(provider):
    st.title("Plugin management")
    try:
        status = provider.manage("status")
    except PluginError as error:
        st.error(str(error))
        return
    st.caption(f"Application: {status['application']} · Core: {status['core']}")
    for field in ("configuration_error", "orphaned_workers", "forward_repair"):
        if status.get(field):
            st.error(field.replace("_", " ").capitalize())
            st.json(status[field])
    if last_operation := st.session_state.get("last_submitted_operation"):
        st.caption(f"Last submitted operation: {last_operation}")
    rows = [
        {
            "Plugin": item["id"],
            "Enabled": item["desired"].get("enabled", False),
            "State": item["runtime"].get("state", "installed"),
            "Healthy": item["health_fresh"],
            "Active": (item["active"] or "")[:12],
            "Candidate": (item["candidate"] or "")[:12],
        }
        for item in status["plugins"]
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption(
        "Active and candidate columns can differ until reload; status health is observed separately."
    )
    if st.button("Refresh status"):
        st.rerun()
    with st.form("install"):
        source = st.text_input(
            "Plugin source",
            placeholder="path:/absolute/plugin or pypi:package==version",
        )
        enable = st.checkbox("Enable after validation", value=False)
        if st.form_submit_button("Install and validate"):
            if not source.strip():
                st.error("Enter a plugin source.")
            else:
                submit(provider, "add", {"source": source.strip(), "enable": enable})
    identifiers = [
        item["id"]
        for item in status["plugins"]
        if item["desired"].get("installed") is not False
    ]
    if identifiers:
        with st.form("manage"):
            identifier = st.selectbox("Plugin", identifiers)
            action = st.selectbox(
                "Operation",
                [
                    "validate",
                    "update",
                    "enable",
                    "reload",
                    "disable",
                    "stop",
                    "remove",
                    "migrate-plan",
                ],
            )
            runtime = st.checkbox("Validate in a temporary runtime", value=False)
            force = st.checkbox("Force stop (interrupts active calls)", value=False)
            if st.form_submit_button("Run operation"):
                params = {
                    "id": identifier,
                    "runtime": runtime,
                    "force": force if action == "stop" else False,
                }
                if action in _PLANNED_ACTIONS and not (action == "stop" and force):
                    result = submit(
                        provider,
                        "plan",
                        {"action": action, "id": identifier},
                    )
                    if result and result.get("id"):
                        st.session_state[_PLAN_OPERATION_KEY] = result["id"]
                else:
                    submit(provider, action, params)
        with st.form("migration"):
            migration_owner = st.selectbox("Migration owner", identifiers)
            plan_id = st.text_input("Reviewed migration plan ID")
            if st.form_submit_button("Apply reviewed migration"):
                if plan_id.strip():
                    submit(
                        provider,
                        "migrate-apply",
                        {"id": migration_owner, "plan_id": plan_id.strip()},
                    )
                else:
                    st.error("Run migrate-plan and review its result first.")
    render_plan_preview(provider)
    st.subheader("Operations")
    for operation in status["operations"][:15]:
        with st.expander(
            f"{operation['kind']} · {operation.get('target') or 'application'} · {operation['status']}"
        ):
            st.json(operation)
            if operation["status"] in ("queued", "running") and st.button(
                "Request cancellation", key=f"cancel-{operation['id']}"
            ):
                submit(provider, "cancel", {"id": operation["id"]})


def submit(provider, action, params):
    try:
        result = provider.manage(action, params)
        operation_id = (
            result.get("id", "complete") if isinstance(result, dict) else "complete"
        )
        if operation_id != "complete":
            st.session_state["last_submitted_operation"] = operation_id
        st.info(f"Operation accepted: {operation_id}. Refresh status for its result.")
        return result
    except PluginError as error:
        st.error(f"{error.code}: {error}")
        return None


def render_plan_preview(provider):
    operation_id = st.session_state.get(_PLAN_OPERATION_KEY)
    if not operation_id:
        return
    try:
        operation = provider.manage("operation", {"id": operation_id})
    except PluginError as error:
        st.error(str(error))
        return
    if not operation:
        st.error(f"Plan operation {operation_id} was not found.")
        return

    st.subheader("Reviewed operation")
    st.caption(f"Plan operation: {operation_id}")
    status = operation.get("status")
    if status in ("queued", "running"):
        st.info(f"Plan operation is {status}; review it again after it completes.")
        st.json(operation)
        return
    if status != "succeeded":
        error = operation.get("error") or {}
        code = error.get("code", "operation_failed")
        message = error.get("message", "The plan operation failed.")
        st.error(f"Plan operation failed ({code}): {message}")
        st.json(operation)
        return

    plan = operation.get("result")
    if not isinstance(plan, dict):
        st.error("Plan operation completed without a reviewable plan.")
        return
    st.success("Plan ready for review.")
    st.write("Affected members", plan.get("affected", []))
    st.write("Missing dependencies", plan.get("missing_dependencies", {}))
    st.write("Migration requirements", plan.get("migrations", {}))
    st.write("Candidate IDs", plan.get("candidates", {}))
    if st.button("Apply reviewed operation"):
        basis = plan.get("basis") or {}
        if (
            not all(
                plan.get(key) is not None for key in ("action", "target", "plan_id")
            )
            or basis.get("revision") is None
        ):
            st.error("The completed plan is missing required apply details.")
            return
        result = submit(
            provider,
            plan["action"],
            {
                "id": plan["target"],
                "plan_id": plan["plan_id"],
                "expected_revision": basis["revision"],
            },
        )
        if result is not None:
            st.session_state.pop(_PLAN_OPERATION_KEY, None)
