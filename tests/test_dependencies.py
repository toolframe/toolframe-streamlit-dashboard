from copy import deepcopy

from test_management import FakeProvider, run_management

from toolframe_streamlit_dashboard.dependencies import graph_dot

REPORT = {
    "schema_version": 1,
    "basis": "selected",
    "nodes": [
        {
            "id": name,
            "label": name,
            "kind": "business",
            "state": "active",
            "healthy": True,
            "version": "1.0.0",
            "definition_source": "selected",
        }
        for name in ("alpha", "storage", "dashboard")
    ]
    + [
        {
            "id": "disabled",
            "label": "disabled",
            "kind": "business",
            "state": "disabled",
            "healthy": False,
            "definition_source": "last_candidate",
        }
    ],
    "edges": [
        {
            "source": "alpha",
            "target": "storage",
            "kind": "required",
            "label": "storage.sql v1",
            "state": "resolved",
        },
        {
            "source": "alpha",
            "target": "dashboard",
            "kind": "presentation",
            "label": "dashboard.page",
            "state": "resolved",
        },
    ],
    "impacts": {
        "alpha": {
            action: {
                "affected": ["alpha", "dashboard"],
                "required_dependents": [],
                "presentation_providers": ["dashboard"],
                "optional_consumers": [],
                "presentations": [
                    {
                        "owner": "alpha",
                        "provider": "dashboard",
                        "kind": "dashboard.page",
                        "resources": ["main"],
                    }
                ],
            }
            for action in ("reload", "disable")
        }
    },
}


class GraphProvider(FakeProvider):
    def access(self, action):
        return {"allowed_scopes": ["system.plugins.read"]}

    def manage(self, action, params=None):
        result = super().manage(action, params)
        if action == "status":
            result["dependency_graph"] = deepcopy(REPORT)
        return result


def test_graph_starts_collapsed_above_hint_and_is_read_only():
    provider = GraphProvider()
    ui = run_management(provider)
    assert not ui.exception
    expander = next(
        item for item in ui.expander if item.label == "Plugin dependencies & impact"
    )
    assert expander.proto.expanded is False
    blocks = list(ui.main.children.values())
    hint = next(
        item for item in ui.caption if item.value.startswith("Disabled plugins remain")
    )
    assert blocks.index(expander) < blocks.index(hint)
    assert len(ui.get("graphviz_chart")) == 1
    assert ui.selectbox(key="dependency-action").disabled
    ui.selectbox(key="dependency-focus").set_value("alpha").run()
    assert not ui.exception
    assert not ui.selectbox(key="dependency-action").disabled
    assert any("alpha, dashboard" in item.value for item in ui.markdown)
    ui.selectbox(key="dependency-action").set_value("disable").run()
    assert not ui.exception
    assert {action for action, _ in provider.calls} == {"status"}
    assert "operation" not in ui.query_params
    ui.selectbox(key="dependency-focus").set_value("disabled").run()
    assert any("outside the selected runtime graph" in item.value for item in ui.info)


def test_empty_and_older_core_reports_do_not_break_management():
    ui = run_management(FakeProvider())
    assert not ui.exception
    assert any("Update core" in item.value for item in ui.info)

    class Empty(GraphProvider):
        def manage(self, action, params=None):
            result = super().manage(action, params)
            if action == "status":
                result["dependency_graph"] = {"nodes": [], "edges": [], "impacts": {}}
            return result

    ui = run_management(Empty())
    assert not ui.exception
    assert any("No plugins" in item.value for item in ui.info)


def test_dot_encodes_labels_and_highlights_separately_from_health():
    report = deepcopy(REPORT)
    report["nodes"][0]["label"] = 'alpha"; <script>'
    report["nodes"][1].update(state="failed", healthy=False)
    report["edges"][0].update(kind="optional", state="missing")
    dot = graph_dot(report, "alpha")
    assert 'alpha\\"; <script>' in dot
    assert "label=<script>" not in dot
    assert 'color="#2563eb"' in dot  # selected
    assert 'color="#ea580c"' in dot  # affected shared provider
    assert 'fillcolor="#ffe4e6"' in dot  # failure is still visible
    assert 'style="dashed"' in dot and 'style="dotted"' in dot
    assert '"alpha" -> "storage"' in dot
