"""Render the host's topology without planning or performing an operation."""

import json
import textwrap

import streamlit as st


def dot_quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def graph_dot(report, focus=None, action="reload"):
    impact = report.get("impacts", {}).get(focus, {}).get(action, {})
    affected = set(impact.get("affected", []))
    optional = set(impact.get("optional_consumers", []))
    entrances = {item["provider"] for item in impact.get("presentations", [])}
    lines = [
        "digraph plugins {",
        'graph [rankdir=TB, bgcolor="transparent", pad=0.12, nodesep=0.2, ranksep=0.35];',
        'node [shape=box, style="rounded,filled", fontname="sans-serif", fontsize=13, margin="0.16,0.12"];',
        'edge [fontname="sans-serif", fontsize=10, color="#94a3b8", fontcolor="#94a3b8", arrowsize=0.7];',
    ]
    for node in report["nodes"]:
        state = node["state"]
        if node.get("healthy"):
            fill, stroke, health = "#dcfce7", "#15803d", "healthy"
        elif state in {"failed", "blocked", "missing", "ambiguous"}:
            fill, stroke, health = "#ffe4e6", "#be123c", "not ready"
        elif state in {"disabled", "stopped", "removed", "installed"}:
            fill, stroke, health = "#e2e8f0", "#64748b", ""
        else:
            fill, stroke, health = "#fef3c7", "#b45309", "not ready"
        outline, role = stroke, ""
        if node["id"] == focus:
            outline, role = "#2563eb", "selected"
        elif node["id"] in affected:
            outline, role = "#ea580c", "affected"
        elif node["id"] in optional:
            outline, role = "#d97706", "optional consumer"
        elif node["id"] in entrances:
            outline, role = "#a855f7", "entry refresh"
        status = f"{state} · {health}" if health and state != health else state
        name = "\n".join(textwrap.wrap(node["label"], width=18))
        label = f"{name}\n{status}" + (f"\n{role}" if role else "")
        lines.append(
            f"{dot_quote(node['id'])} [label={dot_quote(label)}, "
            f'fillcolor="{fill}", color="{outline}", fontcolor="#0f172a", '
            f"penwidth={3 if role else 1.2}];"
        )
    for edge in report["edges"]:
        kind = edge["kind"]
        style = {"required": "solid", "optional": "dashed", "presentation": "dotted"}[
            kind
        ]
        color = "#a78bfa" if kind == "presentation" else "#94a3b8"
        if edge["state"] == "missing":
            color = "#f87171"
        # Keep the overview readable; exact services and versions are listed in
        # the relationship table. Arrow direction is consumer -> supplier.
        label = edge["label"].split(".")[0] if kind == "presentation" else kind
        lines.append(
            f"{dot_quote(edge['source'])} -> {dot_quote(edge['target'])} "
            f'[label={dot_quote(label)}, style="{style}", color="{color}", '
            f'fontcolor="{color}", minlen={3 if kind == "presentation" else 1}];'
        )
    lines.append("}")
    return "\n".join(lines)


def render_dependencies(status):
    with st.expander("Plugin dependencies & impact", expanded=False):
        st.caption(
            "This graph follows installed plugins and their current state. "
            "Refresh status after installing or changing a plugin. "
            "Creating source with plugin new does not install it; use plugin add first."
        )
        report = status.get("dependency_graph")
        if not report:
            st.info("Update core to view the dependency graph.")
            return
        plugins = [node for node in report["nodes"] if node["kind"] != "unresolved"]
        if not plugins:
            st.info("No plugins are installed yet.")
            return
        left, right = st.columns(2)
        focus = left.selectbox(
            "Inspect plugin",
            [None, *(node["id"] for node in plugins)],
            format_func=lambda name: name or "All plugins",
            key="dependency-focus",
        )
        action = right.selectbox(
            "Impact of",
            ["reload", "disable"],
            key="dependency-action",
            disabled=focus is None,
        )
        st.caption(
            "Arrows point from a plugin to its dependency or presentation provider. "
            "Solid: required · Dashed: optional · Dotted: presentation."
        )
        with st.container(key="dependency-diagram"):
            # Streamlit's chart CSS otherwise overrides DOT's measured text
            # sizes with 9.6px, making a narrow embedded graph hard to read.
            st.html(
                """<style>
                .st-key-dependency-diagram .stGraphVizChart .node text { font-size: 13px; }
                .st-key-dependency-diagram .stGraphVizChart .edge text { font-size: 10px; }
                </style>"""
            )
            st.graphviz_chart(graph_dot(report, focus, action), width="stretch")
        st.caption(
            "Green: healthy · Amber: not ready · Red: blocked / failed / missing · "
            "Gray: inactive. Select a plugin to highlight its impact. "
            "Use the graph's full-screen control for a larger view."
        )
        if focus:
            node = next(node for node in plugins if node["id"] == focus)
            st.caption(
                f"{focus} · {node['state']} · version {node.get('version') or 'unknown'} · "
                f"{node.get('in_flight', 0)} in-flight calls · "
                f"definition: {node['definition_source']}"
            )
            if node.get("blocked_by"):
                st.warning("Blocked by: " + ", ".join(node["blocked_by"]))
            impact = report["impacts"].get(focus, {}).get(action)
            if impact:
                st.markdown("**Restart / stop cohort**")
                st.write(", ".join(impact["affected"]) or "None")
                if impact["presentation_providers"]:
                    st.caption(
                        "Includes shared presentation processes: "
                        + ", ".join(impact["presentation_providers"])
                        + ". Related clients may reconnect."
                    )
                if impact["optional_consumers"]:
                    st.write(
                        "Optional consumers (not restarted): "
                        + ", ".join(impact["optional_consumers"])
                    )
                if impact["presentations"]:
                    st.markdown("**Entries that may reconnect or refresh**")
                    st.dataframe(
                        [
                            {
                                "Plugin": item["owner"],
                                "Provider": item["provider"],
                                "Entry": item["kind"],
                                "Resources": ", ".join(item["resources"]),
                            }
                            for item in impact["presentations"]
                        ],
                        hide_index=True,
                        width="stretch",
                    )
            else:
                st.info(
                    "This plugin is outside the selected runtime graph. Its last known "
                    "declarations are shown; preview enable to inspect an activation."
                )
        st.caption(
            "Read-only view of the selected definitions. Inactive declarations are "
            "not live bindings. A new candidate, changed bindings or other pending "
            "changes can alter the impact; use Preview operation before applying."
        )
        relationships = [
            edge
            for edge in report["edges"]
            if focus is None or focus in (edge["source"], edge["target"])
        ]
        if relationships:
            st.markdown("**Relationships**")
            st.dataframe(
                [
                    {
                        "Plugin": edge["source"],
                        "Dependency / provider": edge["target"],
                        "Relation": edge["kind"],
                        "Service / resource": edge["label"],
                        "Binding": edge["state"],
                    }
                    for edge in relationships
                ],
                hide_index=True,
                width="stretch",
            )
