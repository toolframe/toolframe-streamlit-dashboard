from streamlit.testing.v1 import AppTest


def status():
    return {
        "application": "ready",
        "core": "ready",
        "plugins": [
            {
                "id": "alpha",
                "desired": {"installed": True, "enabled": True},
                "runtime": {"state": "ready"},
                "health_fresh": True,
                "active": "active-candidate",
                "candidate": "staged-candidate",
            }
        ],
        "operations": [],
    }


class FakeProvider:
    def __init__(self, operation):
        self.calls = []
        self.operation = operation

    def manage(self, action, params=None):
        self.calls.append((action, params))
        if action == "status":
            return status()
        if action == "plan":
            return {"id": "plan-operation"}
        if action == "operation":
            return self.operation
        return {"id": "submitted-operation"}


def app(provider):
    from toolframe_streamlit_dashboard.management import render_management

    render_management(provider)


def run_management(provider):
    return AppTest.from_function(app, args=(provider,), default_timeout=10).run()


def select_operation(ui, value):
    next(
        selectbox for selectbox in ui.selectbox if selectbox.label == "Operation"
    ).set_value(value)


def submit_operation(ui):
    next(button for button in ui.button if button.label == "Run operation").click()
    return ui.run()


def test_lifecycle_operations_require_reviewed_plan_before_apply():
    provider = FakeProvider(
        {
            "id": "plan-operation",
            "status": "succeeded",
            "result": {
                "action": "reload",
                "target": "alpha",
                "plan_id": "reviewed-plan",
                "basis": {"revision": 7},
                "affected": ["alpha"],
                "missing_dependencies": {},
                "migrations": {},
                "candidates": {"alpha": "candidate-2"},
            },
        }
    )
    ui = run_management(provider)
    select_operation(ui, "reload")
    ui = submit_operation(ui)

    assert ("plan", {"action": "reload", "id": "alpha"}) in provider.calls
    assert ("operation", {"id": "plan-operation"}) in provider.calls
    assert ui.session_state["plan_operation_id"] == "plan-operation"
    assert any(button.label == "Apply reviewed operation" for button in ui.button)

    next(
        button for button in ui.button if button.label == "Apply reviewed operation"
    ).click()
    ui.run()
    assert (
        "reload",
        {
            "id": "alpha",
            "plan_id": "reviewed-plan",
            "expected_revision": 7,
        },
    ) in provider.calls
    assert "plan_operation_id" not in ui.session_state


def test_failed_plan_shows_stale_plan_and_cannot_apply():
    provider = FakeProvider(
        {
            "id": "plan-operation",
            "status": "failed",
            "error": {
                "code": "stale_plan",
                "message": "Review a fresh plan",
            },
        }
    )
    ui = run_management(provider)
    select_operation(ui, "enable")
    ui = submit_operation(ui)

    assert any("stale_plan" in error.value for error in ui.error)
    assert not any(button.label == "Apply reviewed operation" for button in ui.button)


def test_update_and_force_stop_remain_direct_operations():
    provider = FakeProvider({"id": "unused", "status": "queued"})
    ui = run_management(provider)
    select_operation(ui, "update")
    ui = submit_operation(ui)
    assert (
        "update",
        {"id": "alpha", "runtime": False, "force": False},
    ) in provider.calls

    select_operation(ui, "stop")
    ui.checkbox[2].set_value(True)
    submit_operation(ui)
    assert ("stop", {"id": "alpha", "runtime": False, "force": True}) in provider.calls
    assert not any(
        action == "plan" and params.get("action") == "stop"
        for action, params in provider.calls
    )
