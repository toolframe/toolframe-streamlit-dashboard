"""Check the installed wheel from an isolated interpreter outside the source tree."""

import json
import sys
from importlib import import_module, metadata, resources
from pathlib import Path


def main():
    distribution = metadata.distribution("toolframe-streamlit-dashboard")
    if distribution.version != sys.argv[1]:
        raise RuntimeError("Installed version differs from pyproject.toml")
    modules = (
        "toolframe_streamlit_dashboard",
        "toolframe_streamlit_dashboard.plugin",
        "toolframe_streamlit_dashboard.dependencies",
        "toolframe_streamlit_dashboard.history",
        "toolframe_streamlit_dashboard.management",
        "toolframe_sdk",
        "streamlit",
        "uvicorn",
    )
    locations = {}
    for name in modules:
        module = import_module(name)
        location = Path(module.__file__).resolve()
        if not location.is_relative_to(Path(sys.prefix).resolve()):
            raise RuntimeError(f"{name} was imported outside the clean environment")
        locations[name] = str(location)
    entries = [
        entry
        for entry in distribution.entry_points
        if entry.group == "toolframe.plugins" and entry.name == "streamlit-dashboard"
    ]
    if len(entries) != 1:
        raise RuntimeError("Dashboard plugin entry point is missing or invalid")
    definition = entries[0].load()
    sdk = import_module("toolframe_sdk")
    provider = import_module("toolframe_streamlit_dashboard.plugin").DashboardProvider
    if (
        not isinstance(definition, sdk.PluginDefinition)
        or definition.id != "streamlit-dashboard"
        or definition.provider_kind != "dashboard"
        or sdk.load_object(definition.factory) is not provider
    ):
        raise RuntimeError("Dashboard plugin definition or factory is invalid")
    package = resources.files("toolframe_streamlit_dashboard")
    for name in ("app.py", "chrome.css"):
        if not package.joinpath(name).read_text().strip():
            raise RuntimeError(f"Missing installed asset: {name}")
    for name in ("toolframe-streamlit-dashboard", "toolframe-sdk"):
        origin = json.loads(metadata.distribution(name).read_text("direct_url.json"))
        if not origin["url"].endswith(".whl") or origin.get("dir_info", {}).get(
            "editable"
        ):
            raise RuntimeError(f"{name} was not installed from a wheel")
    print(json.dumps({"version": distribution.version, "imports": locations}, indent=2))


if __name__ == "__main__":
    main()
