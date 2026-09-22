from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest
from toolframe_sdk import PluginError


def ready_plan(action="reload"):
    return {
        "id": "plan-operation",
        "sequence": 1,
        "created": 1789959000,
        "kind": "plan",
        "target": "alpha",
        "request": {"action": action, "id": "alpha"},
        "status": "succeeded",
        "result": {
            "action": action,
            "target": "alpha",
            "plan_id": "reviewed-plan",
            "basis": {"revision": 7},
            "affected": ["alpha", "streamlit-dashboard"],
            "missing_dependencies": {},
            "migrations": {},
            "candidates": {"alpha": "candidate-2"},
        },
    }


class FakeProvider:
    def __init__(self, operation=None):
        self.calls = []
        self.operations = {"plan-operation": deepcopy(operation or ready_plan())}
        self.enabled = True
        self.history = []

    def access(self, action):
        assert action == "presentation"
        return {
            "allowed_scopes": [
                "system.plugins.read",
                "system.plugins.manage",
                "system.migrations.manage",
            ]
        }

    def manage(self, action, params=None):
        self.calls.append((action, params))
        if action == "status":
            return {
                "application": "ready",
                "core": "ready",
                "plugins": [
                    {
                        "id": "alpha",
                        "desired": {"installed": True, "enabled": self.enabled},
                        "runtime": {"state": "active" if self.enabled else "stopped"},
                        "health_fresh": self.enabled,
                        "active": "active-candidate" if self.enabled else None,
                        "candidate": "staged-candidate",
                    }
                ],
                "operations": self.history,
            }
        if action == "plan":
            return {"id": "plan-operation", "status": "queued"}
        if action == "operation":
            return self.operations.get(params["id"])
        if action == "operations":
            rows = self.history
            through = params.get("through")
            if through is None:
                through = max((row["sequence"] for row in rows), default=0)
            selected = [
                row
                for row in rows
                if row["sequence"] <= through
                and all(
                    row.get(field) == (value or None)
                    for field, value in params.items()
                    if field in {"target", "kind", "status"}
                )
            ]
            selected.sort(key=lambda row: row["sequence"], reverse=True)
            size = params.get("page_size", 10)
            pages = max(1, (len(selected) + size - 1) // size)
            page = min(params.get("page", 1), pages)
            return {
                "items": selected[(page - 1) * size : page * size],
                "page": page,
                "page_size": size,
                "pages": pages,
                "total": len(selected),
                "through": through,
                "newer_count": sum(row["sequence"] > through for row in rows),
                "filters": {
                    field: sorted(
                        {row[field] for row in rows if row.get(field) is not None}
                    )
                    for field in ("target", "kind", "status")
                },
            }
        self.operations["submitted-operation"] = {
            "id": "submitted-operation",
            "kind": action,
            "target": params.get("id"),
            "status": "running",
            "phase": "draining",
        }
        return {"id": "submitted-operation", "status": "queued"}


def app(provider):
    from toolframe_streamlit_dashboard.management import render_management

    render_management(provider)


def run_management(provider, query_params=None):
    ui = AppTest.from_function(app, args=(provider,), default_timeout=10)
    ui.query_params.update(query_params or {})
    # Fresh wheel environments may spend more than 10s loading pandas/PyArrow
    # native modules. Allow that on startup; later UI runs retain the 10s limit.
    return ui.run(timeout=60)


def select_operation(ui, value):
    next(
        selectbox for selectbox in ui.selectbox if selectbox.label == "Operation"
    ).set_value(value)
    return ui.run()


def click(ui, label):
    next(button for button in ui.button if button.label == label).click()
    ui.run()
    assert not ui.exception
    return ui


@pytest.mark.parametrize("action", ["enable", "reload", "disable", "stop", "remove"])
def test_lifecycle_preview_is_explicit_and_apply_uses_the_reviewed_plan(action):
    provider = FakeProvider(ready_plan(action))
    ui = select_operation(run_management(provider), action)
    assert not any(button.label == "Run operation" for button in ui.button)
    ui = click(ui, "Preview operation")

    assert ("plan", {"action": action, "id": "alpha"}) in provider.calls
    assert not any(call[0] == action for call in provider.calls)
    assert ui.query_params["operation"] == ["plan-operation"]
    assert any("No changes have been applied" in item.value for item in ui.info)
    assert not ui.success

    # Changing the selector must never retarget an already reviewed plan.
    ui = select_operation(ui, "validate")
    click(ui, f"Apply {action}")
    assert (
        action,
        {"id": "alpha", "plan_id": "reviewed-plan", "expected_revision": 7},
    ) in provider.calls
    assert ui.query_params["operation"] == ["submitted-operation"]
    assert not any(button.label.startswith("Apply " + action) for button in ui.button)
    assert any("In progress" in item.value for item in ui.info)
    assert not ui.success


def test_pending_preview_and_completed_disable_survive_new_browser_sessions():
    operation = ready_plan("disable")
    operation.update(status="running", result=None)
    provider = FakeProvider(operation)
    ui = select_operation(run_management(provider), "disable")
    ui = click(ui, "Preview operation")
    assert any("Preparing preview" in item.value for item in ui.info)
    assert not any(button.label == "Apply disable" for button in ui.button)

    provider.operations["plan-operation"] = ready_plan("disable")
    ui = run_management(provider, ui.query_params)
    ui = click(ui, "Apply disable")
    provider.operations["submitted-operation"].update(status="succeeded")
    provider.enabled = False

    # Dashboard worker/session replacement loses all Session State, but keeps
    # the URL and reads the original durable operation instead of submitting again.
    ui = run_management(provider, ui.query_params)
    assert any("Completed: disable · alpha" in item.value for item in ui.success)
    assert not ui.dataframe[0].value.iloc[0]["Enabled"]
    assert ui.dataframe[0].value.iloc[0]["State"] == "stopped"
    assert len([call for call in provider.calls if call[0] == "disable"]) == 1


def test_disabled_plugin_defaults_to_enable_instead_of_reload():
    provider = FakeProvider(ready_plan("enable"))
    provider.enabled = False
    ui = run_management(provider)
    selector = next(item for item in ui.selectbox if item.label == "Operation")
    assert selector.value == "enable"
    assert "reload" not in selector.options
    assert any("Enable it to restore" in item.value for item in ui.caption)
    click(ui, "Preview operation")
    assert ("plan", {"action": "enable", "id": "alpha"}) in provider.calls
    click(ui, "Apply enable")
    assert provider.calls[-1][0] != "reload"
    assert any(action == "enable" for action, _ in provider.calls)


def test_plan_that_completes_during_poll_reruns_into_an_apply_button():
    class FinishingProvider(FakeProvider):
        reads = 0

        def manage(self, action, params=None):
            result = super().manage(action, params)
            if action == "operation":
                self.reads += 1
                if self.reads == 1:
                    return {**result, "status": "running", "result": None}
            return result

    provider = FinishingProvider(ready_plan("disable"))
    ui = run_management(provider, {"operation": "plan-operation"})
    assert not ui.exception
    assert any(button.label == "Apply disable" for button in ui.button)
    assert not any(call[0] == "disable" for call in provider.calls)


def test_failed_plan_shows_stale_plan_and_cannot_apply():
    operation = ready_plan("enable")
    operation.update(
        status="failed",
        error={"code": "stale_plan", "message": "Review a fresh plan"},
    )
    provider = FakeProvider(operation)
    ui = select_operation(run_management(provider), "enable")
    ui = click(ui, "Preview operation")
    assert any("stale_plan" in error.value for error in ui.error)
    assert any("Create a new preview" in item.value for item in ui.info)
    assert not any(button.label == "Apply enable" for button in ui.button)


@pytest.mark.parametrize("status", ["failed", "failed_recovered", "cancelled"])
def test_unsuccessful_apply_is_not_reported_as_success(status):
    provider = FakeProvider()
    provider.operations["apply-operation"] = {
        "id": "apply-operation",
        "kind": "disable",
        "target": "alpha",
        "status": status,
        "error": {"code": status, "message": "The operation did not complete"},
    }
    ui = run_management(provider, {"operation": "apply-operation"})
    assert any(f"disable · alpha · {status}" in error.value for error in ui.error)
    assert not ui.success
    assert not any(button.label == "Apply disable" for button in ui.button)


def test_action_specific_options_and_direct_operations():
    provider = FakeProvider()
    ui = select_operation(run_management(provider), "disable")
    assert not any("Force stop" in item.label for item in ui.checkbox)
    assert not any("temporary runtime" in item.label for item in ui.checkbox)
    ui = select_operation(ui, "update")
    ui = click(ui, "Run operation")
    assert ("update", {"id": "alpha"}) in provider.calls

    ui = select_operation(ui, "stop")
    next(item for item in ui.checkbox if "Force stop" in item.label).set_value(True)
    ui.run()
    click(ui, "Run operation")
    assert ("stop", {"id": "alpha", "force": True}) in provider.calls
    assert not any(
        action == "plan" and params.get("action") == "stop"
        for action, params in provider.calls
    )


def test_history_can_reopen_a_preview_without_submitting_it_again():
    provider = FakeProvider(ready_plan("disable"))
    provider.history = [provider.operations["plan-operation"]]
    ui = run_management(provider)
    ui = click(ui, "Review preview")
    assert ui.query_params["operation"] == ["plan-operation"]
    assert any(button.label == "Apply disable" for button in ui.button)
    assert not any(action in ("plan", "disable") for action, _ in provider.calls)


def test_missing_operation_and_management_errors_are_visible():
    provider = FakeProvider()
    ui = run_management(provider, {"operation": "missing"})
    assert any("was not found" in item.value for item in ui.error)

    class BrokenProvider(FakeProvider):
        def manage(self, action, params=None):
            if action == "plan":
                raise PluginError("busy", "Another operation is running")
            return super().manage(action, params)

    ui = select_operation(run_management(BrokenProvider()), "disable")
    ui = click(ui, "Preview operation")
    assert any("busy" in item.value for item in ui.error)
    assert not ui.success
    assert "operation" not in ui.query_params


def test_malformed_preview_has_no_apply_button():
    operation = ready_plan("disable")
    del operation["result"]["basis"]
    ui = run_management(FakeProvider(operation), {"operation": "plan-operation"})
    assert any("missing required apply details" in item.value for item in ui.error)
    assert not any(button.label == "Apply disable" for button in ui.button)


def test_read_only_diagnostics_cannot_cancel_or_apply_operations():
    class Reader(FakeProvider):
        def access(self, action):
            return {"allowed_scopes": ["system.plugins.read"]}

    operation = ready_plan("disable")
    operation.update(status="running", result=None)
    provider = Reader(operation)
    ui = run_management(provider, {"operation": "plan-operation"})
    assert not ui.exception
    assert next(
        button for button in ui.button if button.label == "Request cancellation"
    ).disabled
    assert not any(button.label == "Install and validate" for button in ui.button)
    provider.operations["plan-operation"] = ready_plan("disable")
    ui.run()
    assert next(
        button for button in ui.button if button.label == "Apply disable"
    ).disabled
