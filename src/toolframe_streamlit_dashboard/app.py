"""Executed by Streamlit in its normal script thread."""

from functools import partial
from html import escape
from pathlib import Path

import streamlit as st
from toolframe_sdk import PluginError

from toolframe_streamlit_dashboard.management import render_management
from toolframe_streamlit_dashboard.plugin import current

provider = current()
epoch, pages = provider.snapshot
st.set_page_config(page_title="Toolframe", layout="wide")
st.html(Path(__file__).with_name("chrome.css"))


@st.fragment(run_every=1)
def access_header():
    try:
        current_access = provider.access("presentation")
    except PluginError as error:
        st.error(error.message)
        return
    if current_access["local_control"]:
        st.caption("Local control")
    if current_access["mode"] == "public":
        reason = (
            "Auth unavailable: " + current_access.get("detail", "")
            if current_access["reason"] == "auth_unavailable"
            else "Public business access"
        )
        st.warning("Public access mode · " + reason)
    elif current_access["mode"] == "waiting":
        st.info("Access is preparing. Reconnecting shortly…")
    else:
        st.caption("Protected access")


try:
    access = provider.access("presentation")
except PluginError as error:
    st.error(error.message)
    st.stop()
access_header()
if access["actor"] in {"password", "operator", "user"}:
    st.markdown(
        f'<form method="post" action="{escape(provider.logout_url(access), quote=True)}"><button type="submit">Sign out</button></form>',
        unsafe_allow_html=True,
    )
else:
    st.link_button("Sign in", access["login_url"])
for target, url in access.get("links", {}).items():
    if target.startswith("web."):
        st.link_button(target, url)
navigation = [
    st.Page(
        partial(provider.render_page, page, epoch),
        title=page.resource.resource.title or page.resource.resource.id,
        url_path=f"{page.resource.owner}--{page.resource.resource.id}",
    )
    for page in pages
    if set(page.resource.resource.required_scopes) <= set(access["allowed_scopes"])
]
if "system.plugins.read" in access["allowed_scopes"]:
    navigation.append(
        st.Page(
            partial(render_management, provider),
            title="Plugin management",
            url_path="plugins",
        )
    )
if navigation:
    st.navigation(navigation).run()
else:
    st.info("No Dashboard pages are available for this access grant.")
