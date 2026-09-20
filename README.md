# Toolframe Streamlit Dashboard

This provider runs one native Streamlit process for the shared UI environment.
Business plugins contribute synchronous `render(context)` pages; navigation and
plugin management are provided here. Pages use the SDK's synchronous
`context.services.require(name, version=1).call(method, params)` proxy.
The Streamlit toolbar uses viewer mode, hiding its Deploy and developer controls.
Plugin lifecycle operations remain available on the Toolframe management page.

Core resolves the provider and all contributing plugin wheels (with their `ui`
extras) together before replacing the worker. Changing any page package replaces
the whole Dashboard. Browser sessions reconnect and session state may reset;
business services and their persisted data remain independently owned.

The provider binds an ephemeral private loopback port and reports it to core.
Core owns the stable `/` gateway, management credentials and HTTP/WebSocket
admission. Streamlit owns its server lifespan and script threads. A stuck script
thread is a cleanup failure, never a successful in-process code reload.

`prepare` imports and validates page entry points without rendering them. A
catalog epoch becomes visible only on `commit`; `abort` preserves live navigation.
The management page submits operations to core and reads their journal; it does
not install packages or access SQLite itself.

For enable, reload, disable, stop and remove, choose **Preview operation**, review
the affected plugins, then choose **Apply enable/reload/disable/stop/remove**.
A preview does not change plugin state. Only stop offers the separate force-stop
option; temporary runtime validation is offered only for validate.

Pending operations update automatically. Completion or errors appear beside the
controls, and the operation ID stays in the page URL so a browser refresh or
Dashboard replacement can resume reading its result. Operation history can reopen
a preview or result. Disabled plugins remain in the management list for re-enabling;
their pages and tools disappear after the disable operation completes.

Development: `uv sync --group dev`, `uv run pytest -q`, `uv build --no-sources`.
Each lifecycle integration test uses a fresh subprocess because Streamlit's
runtime singleton belongs to the process, not a reloadable plugin object.
