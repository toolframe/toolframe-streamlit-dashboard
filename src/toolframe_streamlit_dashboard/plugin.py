from __future__ import annotations

import asyncio
import inspect
import threading
from dataclasses import dataclass
from pathlib import Path

from toolframe_sdk import (
    AuthorizationSpec,
    OwnedResource,
    PageContext,
    Plugin,
    PluginDefinition,
    PluginError,
    load_object,
)
from toolframe_sdk.web import public_base

_current = None


def current():
    if _current is None:
        raise PluginError("dashboard_unavailable", "Dashboard runtime is not active")
    return _current


@dataclass(frozen=True)
class Page:
    resource: OwnedResource
    render: object


class DashboardProvider(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self.server = None
        self.url = None
        self.loop = None
        self.snapshot = (None, ())
        self.staged = {}

    def public_base(self):
        if self.context.endpoints.get("profile") != "gateway-v2":
            return ""
        try:
            return public_base(self.context.endpoints["public_base"]).strip("/")
        except (KeyError, ValueError, TypeError) as error:
            raise PluginError(
                "gateway_endpoints_invalid", "Invalid Dashboard public_base"
            ) from error

    def logout_url(self, access):
        return access.get("logout_url", "/_toolframe/auth/logout")

    async def activate(self):
        global _current
        from streamlit import config
        from streamlit.web.server import Server

        self.loop = asyncio.get_running_loop()
        for name, value in {
            "server.address": "127.0.0.1",
            "server.port": 0,
            "server.baseUrlPath": self.public_base(),
            "server.headless": True,
            "server.fileWatcherType": "none",
            "server.runOnSave": False,
            "server.enableStaticServing": False,
            "browser.gatherUsageStats": False,
            "client.toolbarMode": "viewer",
        }.items():
            config.set_option(name, value)
        _current = self
        self.server = Server(str(Path(__file__).with_name("app.py")), is_hello=False)
        await self.server.start()
        self.url = f"http://127.0.0.1:{config.get_option('server.port')}"

    async def health(self):
        return {
            "runtime": "ready",
            "capabilities": ["gateway-endpoints-v1"],
            "public_base": "/" + self.public_base(),
            "business": "not_provided",
            "http_url": self.url,
            "epoch": self.snapshot[0],
            "pages": [page.resource.key for page in self.snapshot[1]],
        }

    async def dispose(self):
        global _current
        if self.server:
            self.server.stop()
            async with asyncio.timeout(8):
                await self.server.stopped
            threads = [
                thread
                for thread in threading.enumerate()
                if thread.name.startswith("ScriptRunner.scriptThread")
            ]
            for thread in threads:
                await asyncio.to_thread(thread.join, 1)
            if any(thread.is_alive() for thread in threads):
                raise PluginError(
                    "cleanup_failed", "A Streamlit script thread has not exited"
                )
        if _current is self:
            _current = None
        await super().dispose()

    async def prepare(self, resources, epoch):
        pages, seen = [], set()
        for resource in resources:
            if resource.resource.kind != "dashboard.page":
                raise PluginError(
                    "unsupported_resource",
                    "Dashboard accepts whole-page resources only",
                )
            if resource.key in seen:
                raise PluginError("duplicate_resource", resource.key)
            seen.add(resource.key)
            render = load_object(resource.resource.data["entrypoint"])
            if not callable(render) or inspect.iscoroutinefunction(render):
                raise PluginError(
                    "invalid_page",
                    "Page render(context) must be a synchronous callable",
                )
            pages.append(Page(resource, render))
        self.staged[epoch] = tuple(
            sorted(
                pages,
                key=lambda page: (
                    page.resource.resource.data.get("order", 0),
                    page.resource.key,
                ),
            )
        )
        return {"epoch": epoch}

    async def commit(self, epoch):
        if epoch not in self.staged:
            raise PluginError("unknown_epoch", "No prepared page cohort for this epoch")
        self.snapshot = (epoch, self.staged.pop(epoch))
        return {"epoch": epoch}

    async def abort(self, epoch):
        self.staged.pop(epoch, None)
        return {"epoch": epoch}

    def render_page(self, page, epoch):
        access = self.access("presentation")
        if not set(page.resource.resource.required_scopes) <= set(
            access["allowed_scopes"]
        ):
            raise PluginError("forbidden", "This page requires additional scopes")
        page.render(
            PageContext(
                self.context,
                page.resource,
                epoch,
                self.loop,
                access_context=self.access_context(),
                access=access,
            )
        )

    def access_context(self):
        import streamlit as st

        reference = st.context.headers.get("X-Toolframe-Context")
        if not reference:
            raise PluginError(
                "authentication_required",
                "Open the Dashboard through the Toolframe application URL",
            )
        return reference

    def access(self, action, params=None):
        return asyncio.run_coroutine_threadsafe(
            self.context.access(action, params, access_context=self.access_context()),
            self.loop,
        ).result(timeout=30)

    def manage(self, action, params=None):
        future = asyncio.run_coroutine_threadsafe(
            self.context.manage(action, params, access_context=self.access_context()),
            self.loop,
        )
        try:
            return future.result(timeout=30)
        except TimeoutError:
            future.cancel()
            raise PluginError(
                "management_timeout",
                "Management request timed out; inspect operation history before retrying",
            ) from None


plugin = PluginDefinition(
    id="streamlit-dashboard",
    kind="provider",
    provider_kind="dashboard",
    factory="toolframe_streamlit_dashboard.plugin:DashboardProvider",
    authorization=AuthorizationSpec(),
)
