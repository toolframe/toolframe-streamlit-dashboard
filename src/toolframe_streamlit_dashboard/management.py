"""Thin UI over host management operations, with no installer or database logic."""

import streamlit as st
from toolframe_sdk import PluginError


def render_management(provider):
    st.title("Plugin management")
    try:
        status = provider.manage("status")
    except PluginError as error:
        st.error(str(error))
        return
    st.caption(f"Application: {status['application']} · Core: {status['core']}")
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
                submit(
                    provider,
                    action,
                    {
                        "id": identifier,
                        "runtime": runtime,
                        "force": force if action == "stop" else False,
                    },
                )
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
        st.info(
            f"Operation accepted: {result.get('id', 'complete')}. Refresh status for its result."
        )
    except PluginError as error:
        st.error(str(error))
