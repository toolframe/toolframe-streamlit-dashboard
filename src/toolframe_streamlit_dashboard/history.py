"""Paged journal queries with permanent record numbers and browser-local time."""

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st
from toolframe_sdk import PluginError

_PREFIX = "operation_history_"


def reset_history():
    st.session_state[_PREFIX + "page"] = 1
    st.session_state[_PREFIX + "through"] = None


def move_page(page):
    st.session_state[_PREFIX + "page"] = page


def local_timestamp(value):
    if value is None:
        return "Time unavailable"
    zone = UTC
    name, offset = st.context.timezone, st.context.timezone_offset
    if name:
        try:
            zone = ZoneInfo(name)
        except ZoneInfoNotFoundError, ValueError:
            name = None
    if not name and offset is not None and -1440 < offset < 1440:
        zone = timezone(-timedelta(minutes=offset))
    return datetime.fromtimestamp(value, zone).strftime("%Y-%m-%d %H:%M:%S %Z")


def render_history(provider, permissions, track_operation, submit):
    st.subheader("Operations")
    state = st.session_state
    params = {
        "page": state.get(_PREFIX + "page", 1),
        "page_size": state.get(_PREFIX + "page_size", 10),
        "through": state.get(_PREFIX + "through"),
    }
    selectors = (
        ("target", "Filter by plugin", "All plugins"),
        ("kind", "Filter by action", "All actions"),
        ("status", "Filter by result", "All results"),
    )
    for field, _, all_label in selectors:
        choice = state.get(_PREFIX + field, all_label)
        if choice != all_label:
            params[field] = (
                "" if field == "target" and choice == "Application" else choice
            )
    try:
        result = provider.manage("operations", params)
    except PluginError as error:
        st.error(f"Unable to load operation history: {error.message}")
        return
    state[_PREFIX + "page"] = result["page"]
    state[_PREFIX + "through"] = result["through"]
    for column, (field, label, all_label) in zip(st.columns(3), selectors):
        options = [all_label] + (["Application"] if field == "target" else [])
        options += result["filters"][field]
        selected = state.get(_PREFIX + field, all_label)
        if selected not in options:
            options.append(selected)
        with column:
            st.selectbox(label, options, key=_PREFIX + field, on_change=reset_history)
    size, refresh = st.columns(2)
    with size:
        st.selectbox(
            "Rows per page",
            [10, 25, 50],
            key=_PREFIX + "page_size",
            on_change=reset_history,
        )
    with refresh:
        st.button("Refresh history", on_click=reset_history)
    page, total = result["page"], result["total"]
    first = (page - 1) * result["page_size"] + 1 if total else 0
    last = first + len(result["items"]) - 1 if total else 0
    st.caption(
        f"Newest first · Page {page} of {result['pages']} · {first}–{last} of {total} operations. "
        "Permanent operation numbers; times use your browser's time zone."
    )
    if result["newer_count"]:
        st.info(
            f"{result['newer_count']} newer operations. Refresh history to include them."
        )
    if not result["items"]:
        st.info("No operations match these filters.")
    for operation in result["items"]:
        action = (
            f"plan {operation['request'].get('action', 'apply')}"
            if operation["kind"] == "plan"
            else operation["kind"]
        )
        label = (
            f"#{operation['sequence']} · {local_timestamp(operation['created'])} · "
            f"{action} · {operation.get('target') or 'application'} · {operation['status']}"
        )
        with st.expander(label):
            st.json(operation)
            label = "Review preview" if operation["kind"] == "plan" else "View result"
            if st.button(label, key=f"view-{operation['id']}"):
                track_operation(operation["id"])
            scope = (
                "system.migrations.manage"
                if operation["kind"] in {"migrate-plan", "migrate-apply"}
                else "system.plugins.manage"
            )
            if operation["status"] in {"queued", "running"} and st.button(
                "Request cancellation",
                key=f"cancel-{operation['id']}",
                disabled=scope not in permissions,
            ):
                submit(provider, "cancel", {"id": operation["id"]})
    newer, older = st.columns(2)
    with newer:
        st.button("Newer", disabled=page <= 1, on_click=move_page, args=(page - 1,))
    with older:
        st.button(
            "Older",
            disabled=page >= result["pages"],
            on_click=move_page,
            args=(page + 1,),
        )
