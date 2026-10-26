# Generate a Notes plugin

The distribution also supplies `toolframe-streamlit-dashboard/notes` through its
static authoring manifest. It is the explicit replacement for the earlier default
Notes scaffold; plain `plugin new NAME` now creates Core's provider-free basic
service. A matching local wheel can be inspected and used without a running
application or enabled Dashboard:

```sh
toolframe --home APP template show toolframe-streamlit-dashboard/notes --from wheel:/path/to/toolframe_streamlit_dashboard-0.5.2-py3-none-any.whl --json
toolframe --home APP plugin new notes --from wheel:/path/to/toolframe_streamlit_dashboard-0.5.2-py3-none-any.whl --template toolframe-streamlit-dashboard/notes
```

The template includes managed SQL Notes, a Streamlit page, a read-only MCP resource
and an llms document. Select the desired entrances and access policies, build the
business plugin, and explicitly install/enable the required providers. Retrieving
or generating the template does not change application composition. Index sources
require a published authoring wheel or configured matching local wheels.
`--presentation dashboard` remains a compatibility alias.

The template is MIT-licensed and generated projects retain its license. The
provider remains Apache-2.0; see [NOTICE](../NOTICE). Template upgrades affect future
generation only; edit existing projects directly.
