"""Executed by Streamlit in its normal script thread."""

from functools import partial

import streamlit as st

from toolframe_streamlit_dashboard.management import render_management
from toolframe_streamlit_dashboard.plugin import current

provider = current()
epoch, pages = provider.snapshot
st.set_page_config(page_title="Toolframe", layout="wide")
navigation = [
    st.Page(
        partial(provider.render_page, page, epoch),
        title=page.resource.resource.title or page.resource.resource.id,
        url_path=f"{page.resource.owner}--{page.resource.resource.id}",
    )
    for page in pages
]
navigation.append(
    st.Page(
        partial(render_management, provider),
        title="Plugin management",
        url_path="plugins",
    )
)
st.navigation(navigation).run()
