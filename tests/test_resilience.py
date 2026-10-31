import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from app.upstreams import MAX_RESPONSE_BYTES, UpstreamError, Upstreams
from tests.test_integration import CORE, KEY, SETTINGS, client_for, handler


@pytest.mark.asyncio
async def test_retry_backoff_is_exponential_and_bounded(monkeypatch):
    delays = []
    async def fake_sleep(delay):
        delays.append(delay)
    monkeypatch.setattr("app.upstreams.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.upstreams.random.uniform", lambda a, b: 0)
    settings = replace(SETTINGS, max_attempts=3, backoff_seconds=0.1)
    calls = 0
    def fail(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503)
    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(UpstreamError):
            await Upstreams(client, settings).get("CORE", settings.core_url, "backoff")
    assert calls == 3
    assert delays == [0.1, 0.2]


@pytest.mark.asyncio
async def test_successful_retry_recovers():
    calls = 0
    def recover(request):
        nonlocal calls
        calls += 1
        return httpx.Response(500) if calls == 1 else httpx.Response(200, json=CORE)
    async with httpx.AsyncClient(transport=httpx.MockTransport(recover)) as client:
        result = await Upstreams(client, SETTINGS).get("CORE", SETTINGS.core_url, "recover")
    assert result["id"] == 1
    assert calls == 2


def test_network_error_not_retried():
    calls = 0
    def upstream(request):
        nonlocal calls
        if request.url.host == "core.test":
            calls += 1
            raise httpx.ConnectError("private diagnostic must not escape", request=request)
        return handler(request)
    with client_for(upstream) as client:
        response = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY})
    assert response.status_code == 200
    assert response.json()["warnings"][0]["code"] == "NETWORK_ERROR"
    assert "private diagnostic" not in response.text
    assert calls == 1


def test_redirect_is_not_followed_or_retried():
    calls = 0
    def upstream(request):
        nonlocal calls
        if request.url.host == "core.test":
            calls += 1
            return httpx.Response(302, headers={"Location": "https://different.test/path"})
        return handler(request)
    with client_for(upstream) as client:
        data = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY}).json()
    assert data["warnings"][0]["code"] == "UPSTREAM_HTTP_ERROR"
    assert calls == 1


def test_large_response_is_rejected():
    def upstream(request):
        if request.url.host == "core.test":
            return httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))
        return handler(request)
    with client_for(upstream) as client:
        data = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY}).json()
    assert data["warnings"][0]["code"] == "RESPONSE_TOO_LARGE"


@pytest.mark.asyncio
async def test_total_deadline_bounds_slow_drip_body():
    class Drip(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(100):
                yield b" "
                await asyncio.sleep(0.01)
    calls = 0
    def upstream(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, stream=Drip())
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        with pytest.raises(UpstreamError) as error:
            await asyncio.wait_for(Upstreams(client, SETTINGS).get("CORE", SETTINGS.core_url, "drip"), 0.5)
    assert error.value.code == "TIMEOUT"
    assert calls == 2


def test_all_business_providers_start_concurrently():
    started = set()
    gate = asyncio.Event()
    async def upstream(request):
        started.add(request.url.host)
        if len(started) == 3:
            gate.set()
        await asyncio.wait_for(gate.wait(), 0.2)
        return handler(request)
    settings = replace(SETTINGS, timeout_seconds=0.5)
    with client_for(upstream, settings) as client:
        data = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY}).json()
    assert data["partial"] is False
    assert started == {"core.test", "products.test", "fx.test"}


def test_unstable_timeout_does_not_discard_profile():
    calls = 0
    async def upstream(request):
        nonlocal calls
        if request.url.host == "unstable.test":
            calls += 1
            await asyncio.sleep(1)
            return httpx.Response(200)
        return handler(request)
    settings = replace(SETTINGS, unstable_url="https://unstable.test/delay/6")
    with client_for(upstream, settings) as client:
        response = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY})
    data = response.json()
    assert response.status_code == 200
    assert data["customer"] is not None
    assert data["products"] is not None
    assert data["warnings"][0]["code"] == "TIMEOUT"
    assert calls == 2
