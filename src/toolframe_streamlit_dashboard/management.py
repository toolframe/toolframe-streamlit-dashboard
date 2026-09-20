"""Thin UI over host management operations, with no installer or database logic."""

import streamlit as st
from toolframe_sdk import PluginError

_OPERATION_QUERY_KEY = "operation"
_PLANNED_ACTIONS = {"enable", "reload", "disable", "stop", "remove"}
_PENDING = {"queued", "running"}


def render_management(provider):
    st.title("Plugin management")
    try:
        permissions = provider.access("presentation")["allowed_scopes"]
        status = provider.manage("status")
    except PluginError as error:
        st.error(str(error))
        return
    st.caption(f"Application: {status['application']} · Core: {status['core']}")
    for field in ("configuration_error", "orphaned_workers", "forward_repair"):
        if status.get(field):
            st.error(field.replace("_", " ").capitalize())
            st.json(status[field])
    rows = [
        {
            "Plugin": item["id"],
            "Enabled": item["desired"].get("enabled", False),
            "State": item["runtime"].get("state", "installed"),
            "Healthy": item.get(
                "healthy",
                item["health_fresh"] and item["runtime"].get("state") == "active",
            ),
            "Active": (item["active"] or "")[:12],
            "Candidate": (item["candidate"] or "")[:12],
        }
        for item in status["plugins"]
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption(
        "Disabled plugins remain in this list so you can enable them again. "
        "Their pages and tools are removed when disabling completes."
    )
    if st.button("Refresh status"):
        st.rerun()
    can_manage = "system.plugins.manage" in permissions
    can_migrate = "system.migrations.manage" in permissions
    if not can_manage and not can_migrate:
        st.caption("Read-only plugin diagnostics")
        render_operation(provider)
        st.subheader("Operations")
        for operation in status["operations"][:15]:
            with st.expander(f"{operation['kind']} · {operation['status']}"):
                st.json(operation)
        return
    with st.form("install"):
        source = st.text_input(
            "Plugin source",
            placeholder="path:/absolute/plugin or pypi:package==version",
        )
        enable = st.checkbox("Enable after validation", value=False)
        if st.form_submit_button("Install and validate", disabled=not can_manage):
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
        with st.container(border=True):
            identifier = st.selectbox("Plugin", identifiers)
            action = st.selectbox(
                "Operation",
                (
                    [
                        "validate",
                        "update",
                        "enable",
                        "reload",
                        "disable",
                        "stop",
                        "remove",
                    ]
                    if can_manage
                    else []
                )
                + (["migrate-plan"] if can_migrate else []),
            )
            params = {"id": identifier}
            if action == "validate":
                params["runtime"] = st.checkbox(
                    "Validate in a temporary runtime", value=False
                )
            if action == "stop":
                params["force"] = st.checkbox(
                    "Force stop (interrupts active calls)", value=False
                )
            planned = action in _PLANNED_ACTIONS and not params.get("force", False)
            if planned:
                st.caption(
                    "First preview the affected plugins, then apply the operation below. "
                    "Creating a preview does not change plugin state."
                )
            label = "Preview operation" if planned else "Run operation"
            if st.button(label):
                if planned:
                    submit(
                        provider,
                        "plan",
                        {"action": action, "id": identifier},
                    )
                else:
                    submit(provider, action, params)
            render_operation(provider)
        with st.form("migration"):
            migration_owner = st.selectbox("Migration owner", identifiers)
            plan_id = st.text_input("Reviewed migration plan ID")
            if st.form_submit_button(
                "Apply reviewed migration", disabled=not can_migrate
            ):
                if plan_id.strip():
                    submit(
                        provider,
                        "migrate-apply",
                        {"id": migration_owner, "plan_id": plan_id.strip()},
                    )
                else:
                    st.error("Run migrate-plan and review its result first.")
    if not identifiers:
        render_operation(provider)
    st.subheader("Operations")
    for operation in status["operations"][:15]:
        with st.expander(
            f"{operation['kind']} · {operation.get('target') or 'application'} · {operation['status']}"
        ):
            st.json(operation)
            label = "Review preview" if operation["kind"] == "plan" else "View result"
            if st.button(label, key=f"view-{operation['id']}"):
                track_operation(operation["id"])
            if operation["status"] in _PENDING and st.button(
                "Request cancellation", key=f"cancel-{operation['id']}"
            ):
                submit(provider, "cancel", {"id": operation["id"]})


def submit(provider, action, params):
    try:
        result = provider.manage(action, params)
    except PluginError as error:
        st.error(f"{error.code}: {error}")
        return
    if isinstance(result, dict) and result.get("id"):
        track_operation(result["id"])
    else:
        st.error(
            "Core did not return an operation ID. Check operation history before retrying."
        )


def track_operation(operation_id):
    # A Dashboard replacement clears Session State. The URL survives reconnects
    # and lets a new worker resume reading the durable core operation journal.
    st.query_params[_OPERATION_QUERY_KEY] = operation_id
    st.rerun()


def load_operation(provider, operation_id):
    try:
        operation = provider.manage("operation", {"id": operation_id})
    except PluginError as error:
        st.error(f"{error.code}: {error}")
        return None
    if not operation:
        st.error(f"Operation {operation_id} was not found.")
    return operation


def operation_label(operation):
    action = (
        operation.get("request", {}).get("action", "operation")
        if operation["kind"] == "plan"
        else operation["kind"]
    )
    return f"{action} · {operation.get('target') or 'application'}"


@st.fragment(run_every=1)
def poll_operation(provider, operation_id):
    operation = load_operation(provider, operation_id)
    if not operation:
        return
    if operation["status"] not in _PENDING:
        # Rebuild the status table and navigation, and remove this polling
        # fragment once the operation is terminal.
        st.rerun()
    label = operation_label(operation)
    if operation["kind"] == "plan":
        st.info(f"Preparing preview: {label}. No changes have been applied.")
    else:
        st.info(f"In progress: {label} · {operation.get('phase', operation['status'])}")
    st.caption(
        "Status updates automatically. You can also refresh or reconnect to this page."
    )
    scope = (
        "system.migrations.manage"
        if operation["kind"] in {"migrate-plan", "migrate-apply"}
        else "system.plugins.manage"
    )
    if st.button(
        "Request cancellation",
        key=f"pending-cancel-{operation_id}",
        disabled=scope not in provider.access("presentation")["allowed_scopes"],
    ):
        submit(provider, "cancel", {"id": operation_id})


def render_operation(provider):
    operation_id = st.query_params.get(_OPERATION_QUERY_KEY)
    if not operation_id:
        return
    operation = load_operation(provider, operation_id)
    if not operation:
        return
    st.subheader("Operation result")
    st.caption(f"Operation ID: {operation_id}")
    status = operation["status"]
    if status in _PENDING:
        poll_operation(provider, operation_id)
        return
    label = operation_label(operation)
    if status != "succeeded":
        error = operation.get("error") or {}
        code = error.get("code", "operation_failed")
        message = error.get("message", "The operation did not complete.")
        st.error(f"{label} · {status} ({code}): {message}")
        if code == "stale_plan":
            st.info("Create a new preview to review the current state before applying.")
    elif operation["kind"] == "plan":
        render_plan_preview(provider, operation.get("result"))
    else:
        st.success(f"Completed: {label}.")
    with st.expander("Operation details"):
        st.json(operation)


def render_plan_preview(provider, plan):
    if not isinstance(plan, dict):
        st.error("Plan operation completed without a reviewable plan.")
        return
    basis = plan.get("basis") or {}
    if (
        plan.get("action") not in _PLANNED_ACTIONS
        or not all(plan.get(key) for key in ("target", "plan_id"))
        or basis.get("revision") is None
    ):
        st.error("The completed plan is missing required apply details.")
        return
    st.info(
        f"Preview ready: {plan['action']} · {plan['target']}. "
        "No changes have been applied."
    )
    st.write("Affected plugins", plan.get("affected", []))
    if "streamlit-dashboard" in plan.get("affected", []):
        st.caption("The Dashboard may reconnect while this operation is applied.")
    if plan.get("missing_dependencies"):
        st.write("Missing dependencies", plan["missing_dependencies"])
    if plan.get("migrations"):
        st.write("Migration requirements", plan["migrations"])
    if st.button(
        f"Apply {plan['action']}",
        type="primary",
        disabled="system.plugins.manage"
        not in provider.access("presentation")["allowed_scopes"],
    ):
        submit(
            provider,
            plan["action"],
            {
                "id": plan["target"],
                "plan_id": plan["plan_id"],
                "expected_revision": basis["revision"],
            },
        )
