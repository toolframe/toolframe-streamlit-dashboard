import asyncio
import sys

import httpx
import pytest
from toolframe_sdk import OwnedResource, PluginError, Resource, RuntimeContext
from toolframe_sdk.rpc import RpcPeer

from toolframe_streamlit_dashboard.plugin import DashboardProvider


def page(owner="alpha", identifier="main", entrypoint="builtins:print"):
    return OwnedResource(
        owner=owner,
        generation="g1",
        resource=Resource(
            id=identifier,
            kind="dashboard.page",
            title="Example",
            data={"entrypoint": entrypoint},
        ),
    )


async def test_prepare_abort_and_commit_do_not_execute_pages():
    provider = DashboardProvider(
        RuntimeContext(None, plugin_id="streamlit-dashboard", generation="g1")
    )
    await provider.prepare([page()], "one")
    assert (await provider.health())["pages"] == []
    await provider.abort("one")
    with pytest.raises(PluginError):
        await provider.commit("one")
    await provider.prepare([page()], "two")
    await provider.commit("two")
    assert (await provider.health())["pages"] == ["alpha/dashboard.page/main"]
    with pytest.raises(PluginError):
        await provider.prepare([page(), page()], "bad")
    assert (await provider.health())["epoch"] == "two"
    await provider.prepare([page("beta", "other")], "three")
    await provider.commit("three")
    assert (await provider.health())["pages"] == ["beta/dashboard.page/other"]


async def test_invalid_page_preflight_leaves_existing_catalog():
    provider = DashboardProvider(
        RuntimeContext(None, plugin_id="streamlit-dashboard", generation="g1")
    )
    with pytest.raises(PluginError, match="synchronous"):
        await provider.prepare([page(entrypoint="asyncio:sleep")], "bad")
    assert (await provider.health())["pages"] == []


async def test_real_streamlit_server_is_owned_by_fresh_worker_process():
    async def handler(method, params):
        if method == "management.call":
            return {
                "core": "ready",
                "application": "ready",
                "plugins": [],
                "operations": [],
            }
        raise PluginError("unexpected_call", method)

    for generation in ("first", "replacement"):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "toolframe_sdk.worker",
            "--entrypoint",
            "toolframe_streamlit_dashboard.plugin:plugin",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        peer = RpcPeer(process.stdout, process.stdin, handler)
        reader = asyncio.create_task(peer.run())
        logs = asyncio.create_task(process.stderr.read())
        try:
            assert (await peer.request("runtime.describe"))["definition"][
                "id"
            ] == "streamlit-dashboard"
            health = await peer.request("runtime.activate", {"generation": generation})
            await peer.request(
                "provider.prepare", {"resources": [], "epoch": generation}
            )
            await peer.request("provider.commit", {"epoch": generation})
            async with httpx.AsyncClient(
                base_url=health["http_url"], trust_env=False
            ) as client:
                assert (await client.get("/_stcore/health")).status_code == 200
                assert (await client.get("/")).status_code == 200
            await peer.request("runtime.dispose")
            process.stdin.close()
            assert await asyncio.wait_for(process.wait(), 10) == 0
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
            await peer.close()
            await asyncio.gather(reader, logs, return_exceptions=True)
