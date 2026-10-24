"""Dashboard Notes is an optional distribution-owned template."""

import importlib
import json
import sys
import tomllib
from importlib.metadata import distribution
from importlib.resources import files

from toolframe_streamlit_dashboard.authoring import generate


def test_manifest_template_and_public_contracts(tmp_path, monkeypatch):
    manifest = json.loads(
        distribution("toolframe-streamlit-dashboard").read_text(
            "extra_metadata/toolframe-authoring.json"
        )
    )
    assert manifest["templates"][0]["id"] == "notes"
    generate(destination=tmp_path, parameters={"name": "customer-notes"})
    project = tomllib.loads((tmp_path / "pyproject.toml").read_text())["project"]
    assert project["name"] == "toolframe-customer-notes"
    assert project["entry-points"]["toolframe.plugins"] == {
        "customer-notes": "toolframe_customer_notes.plugin:plugin"
    }
    assert project["license"] == "MIT"
    assert (tmp_path / "LICENSE").read_bytes() == files(
        "toolframe_streamlit_dashboard"
    ).joinpath("templates/notes/LICENSE").read_bytes()
    monkeypatch.syspath_prepend(str(tmp_path / "src"))
    try:
        definition = importlib.import_module("toolframe_customer_notes.plugin").plugin
        assert definition.requires["sql"].service == "toolframe.sql"
        methods = definition.services["customer-notes.notes"].methods
        assert set(methods) == {"capture", "list_notes"}
        assert methods["capture"].required_scopes == ("customer-notes.write",)
        resources = {r.kind: r for r in definition.resources}
        assert (
            resources["dashboard.page"].data["entrypoint"]
            == "toolframe_customer_notes.page:render"
        )
        assert resources["mcp.tool"].data["service"] == "customer-notes.notes"
        assert definition.store.revision == "v1"
    finally:
        for name in tuple(sys.modules):
            if name == "toolframe_customer_notes" or name.startswith(
                "toolframe_customer_notes."
            ):
                del sys.modules[name]
