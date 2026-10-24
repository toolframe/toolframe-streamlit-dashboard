"""Optional Notes authoring; discovery reads distribution metadata only."""

from importlib.resources import files

from toolframe_sdk.authoring import render_plugin, write_template


def generate(*, destination, parameters):
    write_template(
        destination,
        render_plugin(
            files("toolframe_streamlit_dashboard").joinpath("templates/notes"),
            parameters["name"],
        ),
    )
