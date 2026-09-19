# Toolframe Streamlit Dashboard

This provider runs one native Streamlit process for the shared UI environment.
Business plugins contribute synchronous `render(context)` pages; navigation and
plugin management are provided here. Pages use the SDK's synchronous
`context.services.require(name, version=1).call(method, params)` proxy.

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

Development: `uv sync --group dev`, `uv run pytest -q`, `uv build --no-sources`.
Each lifecycle integration test uses a fresh subprocess because Streamlit's
runtime singleton belongs to the process, not a reloadable plugin object.
