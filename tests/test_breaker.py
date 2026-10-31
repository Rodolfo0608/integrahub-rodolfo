import asyncio
from dataclasses import replace

import httpx
import pytest

from app.breaker import CircuitBreaker
from app.upstreams import UpstreamError
from tests.test_integration import KEY, SETTINGS, client_for, handler


@pytest.mark.asyncio
async def test_open_half_open_and_successful_recovery():
    now = [0.0]
    breaker = CircuitBreaker(threshold=2, cooldown=30, clock=lambda: now[0])
    calls = 0
    async def fail():
        nonlocal calls
        calls += 1
        raise UpstreamError("TIMEOUT")
    for _ in range(2):
        with pytest.raises(UpstreamError):
            await breaker.call(fail)
    assert breaker.state == "open"
    with pytest.raises(UpstreamError) as error:
        await breaker.call(fail)
    assert error.value.code == "CIRCUIT_OPEN"
    assert calls == 2
    now[0] = 30
    async def recover():
        return "ok"
    assert await breaker.call(recover) == "ok"
    assert breaker.state == "closed"
    assert breaker.failures == 0


@pytest.mark.asyncio
async def test_only_one_half_open_probe_and_failure_reopens():
    now = [0.0]
    breaker = CircuitBreaker(threshold=1, cooldown=1, clock=lambda: now[0])
    async def fail():
        raise UpstreamError("UPSTREAM_5XX")
    with pytest.raises(UpstreamError):
        await breaker.call(fail)
    now[0] = 1
    started, release = asyncio.Event(), asyncio.Event()
    async def probe():
        started.set()
        await release.wait()
        raise UpstreamError("TIMEOUT")
    task = asyncio.create_task(breaker.call(probe))
    await started.wait()
    with pytest.raises(UpstreamError) as error:
        await breaker.call(fail)
    assert error.value.code == "CIRCUIT_OPEN"
    release.set()
    with pytest.raises(UpstreamError):
        await task
    assert breaker.state == "open"


@pytest.mark.asyncio
async def test_cancelled_probe_can_retry_after_cooldown():
    now = [0.0]
    breaker = CircuitBreaker(threshold=1, cooldown=1, clock=lambda: now[0])
    async def fail():
        raise UpstreamError("TIMEOUT")
    with pytest.raises(UpstreamError):
        await breaker.call(fail)
    now[0] = 1
    started = asyncio.Event()
    async def wait():
        started.set()
        await asyncio.sleep(10)
    task = asyncio.create_task(breaker.call(wait))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert breaker.state == "open"
    now[0] = 2
    async def recover():
        return True
    assert await breaker.call(recover) is True


def test_endpoint_fourth_unstable_call_skips_http_after_three_failures():
    calls = 0
    def upstream(request):
        nonlocal calls
        if request.url.host == "unstable.test":
            calls += 1
            return httpx.Response(500)
        return handler(request)
    settings = replace(SETTINGS, unstable_url="https://unstable.test/status/500")
    with client_for(upstream, settings) as client:
        for _ in range(3):
            client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY})
        data = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY}).json()
        assert client.get("/health", headers={"X-Api-Key": KEY}).json()["unstableCircuit"] == "open"
    assert calls == 6
    assert data["warnings"][0]["code"] == "CIRCUIT_OPEN"
    assert data["customer"] is not None
