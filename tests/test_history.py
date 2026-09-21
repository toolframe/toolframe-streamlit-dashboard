from datetime import UTC, datetime
from types import SimpleNamespace

from test_management import FakeProvider, click, ready_plan, run_management


def provider_with_history(count=65):
    provider = FakeProvider()
    for number in range(1, count + 1):
        item = {
            **ready_plan(),
            "id": f"op-{number}",
            "sequence": number,
            "created": 1789959000 + number,
            "kind": "reload" if number % 2 else "enable",
            "target": "alpha" if number % 3 else "retired",
            "status": "failed" if number % 5 else "succeeded",
        }
        provider.history.append(item)
        provider.operations[item["id"]] = item
    return provider


def history_labels(ui):
    return [item.label for item in ui.expander if item.label.startswith("#")]


def test_history_numbers_pagination_new_arrivals_and_refresh():
    provider = provider_with_history()
    ui = run_management(provider)
    assert not ui.exception
    assert len(history_labels(ui)) == 10
    assert history_labels(ui)[0].startswith("#65 ·")
    assert next(button for button in ui.button if button.label == "Newer").disabled
    ui = click(ui, "Older")
    assert history_labels(ui)[0].startswith("#55 ·")
    assert any("Page 2 of 7" in item.value for item in ui.caption)
    provider.history.append({**provider.history[-1], "id": "new", "sequence": 66})
    ui.run()
    assert history_labels(ui)[0].startswith("#55 ·")
    assert any("1 newer operations" in item.value for item in ui.info)
    click(ui, "Refresh history")
    assert history_labels(ui)[0].startswith("#66 ·")
    assert any("Page 1 of 7" in item.value for item in ui.caption)
    next(
        select for select in ui.selectbox if select.label == "Rows per page"
    ).set_value(50)
    ui.run()
    assert len(history_labels(ui)) == 50
    click(ui, "Older")
    assert history_labels(ui)[0].startswith("#16 ·")
    assert next(button for button in ui.button if button.label == "Older").disabled


def test_combined_history_filters_reset_page_and_keep_record_numbers():
    provider = provider_with_history()
    ui = click(run_management(provider), "Older")
    for label, value in (
        ("Filter by plugin", "retired"),
        ("Filter by action", "enable"),
        ("Filter by result", "succeeded"),
    ):
        next(select for select in ui.selectbox if select.label == label).set_value(
            value
        )
        ui.run()
        assert not ui.exception
    assert [label.split(" ·")[0] for label in history_labels(ui)] == ["#60", "#30"]
    params = [params for action, params in provider.calls if action == "operations"][-1]
    assert (
        params["target"] == "retired"
        and params["kind"] == "enable"
        and params["status"] == "succeeded"
    )
    assert params["page"] == 1
    next(
        select for select in ui.selectbox if select.label == "Filter by plugin"
    ).set_value("Application")
    ui.run()
    assert not history_labels(ui)
    assert any("No operations match" in item.value for item in ui.info)


def test_read_only_history_retains_paging_and_disables_cancellation():
    provider = provider_with_history(11)
    provider.access = lambda action: {"allowed_scopes": ["system.plugins.read"]}
    provider.history[-1]["status"] = "running"
    ui = run_management(provider)
    assert not ui.exception
    assert next(
        button for button in ui.button if button.label == "Request cancellation"
    ).disabled
    click(ui, "Older")
    assert history_labels(ui)[0].startswith("#1 ·")
    click(ui, "View result")
    assert ui.query_params["operation"] == ["op-1"]
    assert not any(
        action not in {"status", "operation", "operations"}
        for action, _ in provider.calls
    )


def test_history_times_follow_browser_zone_with_offset_fallback(monkeypatch):
    from toolframe_streamlit_dashboard import history

    value = datetime(2026, 9, 21, 2, 3, 4, tzinfo=UTC).timestamp()
    monkeypatch.setattr(
        history,
        "st",
        SimpleNamespace(
            context=SimpleNamespace(timezone="Asia/Hong_Kong", timezone_offset=-480)
        ),
    )
    assert history.local_timestamp(value) == "2026-09-21 10:03:04 HKT"
    history.st.context.timezone = "invalid"
    assert history.local_timestamp(value) == "2026-09-21 10:03:04 UTC+08:00"
    history.st.context.timezone_offset = None
    assert history.local_timestamp(value) == "2026-09-21 02:03:04 UTC"
