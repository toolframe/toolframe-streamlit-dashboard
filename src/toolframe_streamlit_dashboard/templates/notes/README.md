# Notes plugin

Store bounded text notes through Toolframe SQL and present them in a Streamlit
Dashboard page. The plugin also declares a read-only MCP list resource and an
llms usage document; install providers only for the entrances you want.

From this source directory:

```sh
uv build --wheel
toolframe --home /path/to/app plugin add path:.
```

Before enabling the plugin, install and enable a SQL provider and the requested
presentation providers. The generated service declares `sample-notes.read` and
`sample-notes.write` scopes. The example's list method is an explicitly public
HTTP API; choose confidential entrance policy and remove public publication when
private notes are required. Notes are shared among authorized callers and do not
provide per-person row isolation.

Generated source belongs to this project. Template package and skill upgrades
do not rewrite it. The accompanying MIT license must be preserved.
