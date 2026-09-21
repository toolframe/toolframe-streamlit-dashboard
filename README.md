# Toolframe Streamlit Dashboard

This provider runs one native Streamlit process for the shared UI environment.
Business plugins contribute synchronous `render(context)` pages; navigation and
plugin management are provided here. Pages use the SDK's synchronous
`context.services.require(name, version=1).call(method, params)` proxy.
The Streamlit toolbar uses viewer mode, hiding its Deploy and developer controls.
Its native running indicator shows a circular spinner instead of cycling sports
icons. The Running label, Stop button and connection indicators remain available;
reduced-motion preferences disable the rotation. The narrowly scoped styling
targets Streamlit 1.61's busy-widget test ID and should be checked on upgrades.
Plugin lifecycle operations remain available on the Toolframe management page.

Core resolves the provider and all contributing plugin wheels (with their `ui`
extras) together before replacing the worker. Changing any page package replaces
the whole Dashboard. Browser sessions reconnect and session state may reset;
business services and their persisted data remain independently owned.

The provider binds an ephemeral private loopback port and reports it to core.
Core owns the stable `/` gateway, management credentials and HTTP/WebSocket
admission. Streamlit owns its server lifespan and script threads. A stuck script
thread is a cleanup failure, never a successful in-process code reload.

SDK 0.2 page contexts carry a host-issued reference for each browser connection.
Pages use `context.can(scope)` to adapt controls; core checks every service call.
Navigation filters page scopes and the plugin-management page requires
`system.plugins.read`. Its mutation controls require the relevant management
scopes. A password without system grants cannot reach these operations through
the bridge. Incoming browser identity headers are not trusted.

The shared header displays local control, protected access or public access with
its reason. It remains present when the separate Dashboard Auth plugin is
unavailable. Its one-second refresh is presentation polling and does not count
as password activity. Use `activity=False` for other background service polling.

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
Disabled plugins default to **enable** and do not offer reload/disable/stop.
Enable restores the installed version; update stages a freshly resolved package.

The **Plugin dependencies & impact** accordion sits directly below the status
table and starts collapsed. It reads core's `dependency_graph` diagnostics
(core 0.4.0+) under the existing `system.plugins.read` permission. Nodes show
Cordis lifecycle state and current health; arrows run from consumer to supplier.
Solid lines are required services, dashed lines optional services, and dotted
lines presentation providers. Missing suppliers and inactive plugins stay visible.

Select a plugin and **reload** or **disable** to highlight the lifecycle cohort,
optional consumers, and page/tool/document entries that may reconnect or refresh.
The cohort comes from core's actual planner. Presentation refreshes do not imply
that the provider or every page's business process restarts. Use the full-screen
control to enlarge the graph; the relationship table includes exact service names
and versions.

This view never installs, validates, submits an operation, or changes composition.
It describes selected versions; inactive declarations are labeled `last_candidate`.
New candidates or pending configuration changes can produce a different plan, so
the existing **Preview operation** / **Apply** workflow remains authoritative.
Refreshing status refreshes the graph too. An older core shows an upgrade hint.

Development: `uv sync --group dev`, `uv run pytest -q`, `uv build --no-sources`.
Each lifecycle integration test uses a fresh subprocess because Streamlit's
runtime singleton belongs to the process, not a reloadable plugin object.
